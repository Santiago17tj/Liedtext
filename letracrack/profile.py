"""Perfil de escritura en memoria.

El servidor no guarda nada: el navegador conserva el perfil y lo envía con cada petición.
Formato de transporte de un glifo: PNG en escala de grises con la tinta OSCURA sobre fondo blanco
(255 - alfa), para que el navegador pueda mostrarlo tal cual.
"""
from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

import cv2
import numpy as np

from . import extract as ex
from . import layout as L

XHEIGHT_CHARS = "acemnorsuvwxz"
MAX_GLYPHS = len(L.CHARSET) * 12
MAX_GLYPH_PX = 220
MAX_PNG_B64 = 80_000


@dataclass
class Glyph:
    char: str
    alpha: np.ndarray  # uint8, 255 = tinta
    bottom_offset: int

    @property
    def h(self) -> int:
        return self.alpha.shape[0]

    @property
    def w(self) -> int:
        return self.alpha.shape[1]


def _encode_png(alpha: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", 255 - alpha, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise ValueError("No se pudo codificar un glifo.")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def scan_photo(data: bytes) -> dict:
    """Procesa una foto de la plantilla y devuelve los glifos en formato de transporte."""
    result = ex.extract_glyphs(ex.decode_image(data))
    if not result.glyphs:
        raise ex.ScanError("No encontré escritura en ningún recuadro. ¿Es la plantilla correcta y está rellena?")
    return {
        "sha1": hashlib.sha1(data).hexdigest(),
        "found": len(result.glyphs),
        "missing": result.missing,
        "warnings": ex.sheet_sanity(result),
        "ink_rgb": list(result.ink_rgb) if result.ink_rgb else None,
        "glyphs": [
            {"char": g.char, "bottom_offset": g.bottom_offset, "w": g.alpha.shape[1], "h": g.alpha.shape[0],
             "png": _encode_png(g.alpha)}
            for g in result.glyphs
        ],
    }


class ProfileData:
    def __init__(self, glyphs: dict[str, list[Glyph]], ink_rgb: tuple[int, int, int] | None):
        self._glyphs = glyphs
        self.ink_rgb = ink_rgb

    @classmethod
    def from_json(cls, d: object) -> "ProfileData":
        if not isinstance(d, dict) or not isinstance(d.get("glyphs"), list):
            raise ValueError("Perfil inválido: falta la lista de letras.")
        items = d["glyphs"]
        if len(items) > MAX_GLYPHS:
            raise ValueError("Perfil demasiado grande.")
        glyphs: dict[str, list[Glyph]] = {}
        for it in items:
            if not isinstance(it, dict):
                raise ValueError("Perfil inválido.")
            ch, png, bo = it.get("char"), it.get("png"), it.get("bottom_offset")
            if not (isinstance(ch, str) and len(ch) == 1 and ch in L.CHARSET):
                raise ValueError("Perfil inválido: carácter desconocido.")
            if not (isinstance(png, str) and len(png) <= MAX_PNG_B64) or not isinstance(bo, int) or abs(bo) > 400:
                raise ValueError("Perfil inválido: glifo mal formado.")
            try:
                raw = base64.b64decode(png, validate=True)
            except Exception as e:  # noqa: BLE001
                raise ValueError("Perfil inválido: imagen de letra corrupta.") from e
            img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
            if img is None or not (3 <= img.shape[0] <= MAX_GLYPH_PX and 3 <= img.shape[1] <= MAX_GLYPH_PX):
                raise ValueError("Perfil inválido: imagen de letra con tamaño no válido.")
            glyphs.setdefault(ch, []).append(Glyph(ch, 255 - img, bo))
        ink = d.get("ink_rgb")
        if ink is not None:
            if not (isinstance(ink, list) and len(ink) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in ink)):
                raise ValueError("Perfil inválido: color de tinta.")
            ink = tuple(ink)
        return cls(glyphs, ink)

    def glyphs(self) -> dict[str, list[Glyph]]:
        return self._glyphs

    def xheight(self) -> float:
        hs = [g.h - 4 for ch in XHEIGHT_CHARS for g in self._glyphs.get(ch, [])]
        return float(np.median(hs)) if hs else 0.0

    def stroke_width(self) -> float:
        ws = [ex.estimate_stroke_width(g.alpha) for gs in self._glyphs.values() for g in gs[:1]]
        return float(np.median(ws)) if ws else 2.5
