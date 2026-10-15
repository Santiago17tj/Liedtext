"""Motor de composición: texto + perfil de escritura -> páginas manuscritas."""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
import cv2
import numpy as np
from PIL import Image

from . import layout as L
from . import paper as P
from .profile import Glyph, ProfileData

TIGHT_BEFORE = set(".,;:!?)%")
TIGHT_AFTER = set("(¿¡")
CHAR_MAP = {
    "“": '"', "”": '"', "«": '"', "»": '"', "„": '"',
    "‘": "'", "’": "'", "´": "'", "`": "'",
    "–": "-", "—": "-", "−": "-", "‐": "-", "‑": "-",
    "•": "-", "·": "-", "▪": "-",
    " ": " ", "\t": "    ", "\r": "",
}
INK_PRESETS = {"blue": (28, 58, 150), "black": (24, 24, 30)}
DEFAULT_INK = (28, 45, 120)
DEFAULT_SIZE_MM = {"rayado": 3.0, "cuadriculado": 2.3, "blanco": 3.2}


@dataclass
class RenderOptions:
    paper: str = "rayado"
    size_mm: float | None = None  # altura de la «x» minúscula; None = según el papel
    line_mm: float | None = None
    top_mm: float = 25.0
    left_mm: float = 30.0
    right_mm: float = 10.0
    bottom_mm: float = 14.0
    spacing: float = 0.10      # espacio entre letras, en alturas de «x»
    naturalness: float = 1.0   # 0 = perfectamente regular, 1 = variación humana, >1 = descuidada
    ink: str = "profile"       # profile | blue | black | #rrggbb
    seed: int | None = None
    realism: bool = True


@dataclass
class _Item:
    glyph: Glyph
    x: float      # borde izquierdo de la tinta, relativo al inicio de la palabra
    scale: float
    theta: float
    dy: float


@dataclass
class _Word:
    items: list[_Item]
    width: float


@dataclass
class _Line:
    words: list[tuple[float, _Word]]  # (x relativo al margen izquierdo, palabra)
    scale: float
    title: bool = False
    blank: bool = False


@dataclass
class Report:
    pages: int = 0
    chars: int = 0
    missing: list[str] = field(default_factory=list)
    substituted: dict[str, str] = field(default_factory=dict)


def resolve_ink(opt: str, profile: ProfileData) -> tuple[int, int, int]:
    if opt in INK_PRESETS:
        return INK_PRESETS[opt]
    if re.fullmatch(r"#[0-9a-fA-F]{6}", opt or ""):
        return tuple(int(opt[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    return profile.ink_rgb or DEFAULT_INK


def _strip_marks(ch: str) -> str:
    return unicodedata.normalize("NFD", ch)[0]


class _Composer:
    def __init__(self, profile: ProfileData, opt: RenderOptions):
        self.profile = profile
        self.opt = opt
        self.glyphs = profile.glyphs()
        self.xh = profile.xheight()
        if not self.glyphs or self.xh <= 0:
            raise ValueError("El perfil aún no tiene muestras suficientes (faltan letras minúsculas).")
        self.seed = opt.seed if opt.seed is not None else int(np.random.SeedSequence().entropy % 2**31)
        self.rng = np.random.default_rng(self.seed)
        self.nat = max(0.0, opt.naturalness)
        size_mm = opt.size_mm or DEFAULT_SIZE_MM.get(opt.paper, 3.0)
        self.s0 = size_mm * L.PX_PER_MM / self.xh
        self.xh_px = size_mm * L.PX_PER_MM
        self.last_variant: dict[str, int] = {}
        self.report = Report()

    # ---- elección de glifos -------------------------------------------
    def _lookup(self, ch: str) -> tuple[list[Glyph] | None, str]:
        if ch in self.glyphs:
            return self.glyphs[ch], ch
        base = _strip_marks(ch)
        if base != ch and base in self.glyphs:
            self.report.substituted[ch] = base
            return self.glyphs[base], base
        for alt in (ch.lower(), ch.upper()):
            if alt in self.glyphs:
                self.report.substituted[ch] = alt
                return self.glyphs[alt], alt
        return None, ch

    def _pick(self, key: str, options: list[Glyph]) -> Glyph:
        if len(options) == 1:
            return options[0]
        last = self.last_variant.get(key, -1)
        pool = [i for i in range(len(options)) if i != last]
        i = int(self.rng.choice(pool))
        self.last_variant[key] = i
        return options[i]

    # ---- palabras -------------------------------------------------------
    def build_word(self, text: str, scale: float) -> _Word:
        items: list[_Item] = []
        x = 0.0
        prev: str | None = None
        for ch in text:
            options, key = self._lookup(ch)
            if options is None:
                if ch not in self.report.missing:
                    self.report.missing.append(ch)
                continue
            g = self._pick(key, options)
            s = scale * (1 + self.rng.normal(0, 0.03 * self.nat))
            if prev is not None:
                gap = self.opt.spacing * self.xh_px * (scale / self.s0) * (1 + self.rng.normal(0, 0.35 * self.nat))
                if ch in TIGHT_BEFORE:
                    gap *= 0.3
                if prev in TIGHT_AFTER:
                    gap *= 0.3
                x += max(gap, -0.05 * self.xh_px)
            items.append(_Item(g, x, s, float(self.rng.normal(0, 1.3 * self.nat)),
                               float(self.rng.normal(0, 0.035 * self.nat) * self.xh_px)))
            x += (g.w - 4) * s
            prev = ch
            self.report.chars += 1
        return _Word(items, x)

    def space_px(self, scale: float) -> float:
        base = 0.55 + 0.2 * float(self.rng.random()) * self.nat
        return base * self.xh_px * (scale / self.s0)

    @staticmethod
    def _split_word(word: _Word, max_w: float) -> list[_Word]:
        out, cur, start = [], [], 0.0
        for it in word.items:
            right = it.x + (it.glyph.w - 4) * it.scale
            if cur and right - start > max_w:
                out.append(_Word([_Item(i.glyph, i.x - start, i.scale, i.theta, i.dy) for i in cur], cur[-1].x - start + (cur[-1].glyph.w - 4) * cur[-1].scale))
                cur, start = [], it.x
            cur.append(it)
        if cur:
            out.append(_Word([_Item(i.glyph, i.x - start, i.scale, i.theta, i.dy) for i in cur], cur[-1].x - start + (cur[-1].glyph.w - 4) * cur[-1].scale))
        return out

    # ---- párrafos y líneas ---------------------------------------------
    def layout(self, text: str, avail_w: float) -> list[_Line]:
        for k, v in CHAR_MAP.items():
            text = text.replace(k, v)
        text = text.replace("…", "...")
        lines: list[_Line] = []
        for raw in text.split("\n"):
            if not raw.strip():
                lines.append(_Line([], self.s0, blank=True))
                continue
            title = False
            body = raw.rstrip()
            lead = len(body) - len(body.lstrip(" "))
            body = body.lstrip(" ")
            if body.startswith("# "):
                title, body = True, body[2:].strip()
            scale = self.s0 * (1.25 if title else 1.0)
            indent = min(lead * 2.0 * L.PX_PER_MM, 30 * L.PX_PER_MM)
            bullet = re.match(r"^[-*]\s+(.*)$", body)
            words_txt = body.split()
            cont_indent = indent
            if bullet:
                words_txt = ["-"] + bullet.group(1).split()
                b = self.build_word("-", scale)
                cont_indent = indent + b.width + self.space_px(scale)
            cur: list[tuple[float, _Word]] = []
            x = indent
            for wt in words_txt:
                word = self.build_word(wt, scale)
                if not word.items:
                    continue
                sp = self.space_px(scale) if cur else 0.0
                if cur and x + sp + word.width > avail_w:
                    lines.append(_Line(cur, scale, title))
                    cur, x, sp = [], cont_indent, 0.0
                pieces = [word]
                if word.width > avail_w - x:
                    pieces = self._split_word(word, max(avail_w - x, 60))
                for j, pc in enumerate(pieces):
                    if j > 0:
                        lines.append(_Line(cur, scale, title))
                        cur, x, sp = [], cont_indent, 0.0
                    cur.append((x + sp, pc))
                    x += sp + pc.width
            if cur:
                lines.append(_Line(cur, scale, title))
        return lines


def _paste(ink: np.ndarray, alpha: np.ndarray, cx: float, cy: float, s: float, theta: float) -> None:
    h, w = alpha.shape
    w2, h2 = max(1, round(w * s)), max(1, round(h * s))
    scaled = cv2.resize(alpha, (w2, h2), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    M = cv2.getRotationMatrix2D((w2 / 2, h2 / 2), theta, 1.0)
    nw = int(math.ceil(h2 * abs(M[0, 1]) + w2 * abs(M[0, 0]))) + 2
    nh = int(math.ceil(h2 * abs(M[1, 1]) + w2 * abs(M[1, 0]))) + 2
    x0, y0 = math.floor(cx - nw / 2), math.floor(cy - nh / 2)
    M[0, 2] += (cx - x0) - w2 / 2
    M[1, 2] += (cy - y0) - h2 / 2
    patch = cv2.warpAffine(scaled.astype(np.float32) / 255.0, M, (nw, nh), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    x1, y1 = x0 + nw, y0 + nh
    cx0, cy0, cx1, cy1 = max(x0, 0), max(y0, 0), min(x1, ink.shape[1]), min(y1, ink.shape[0])
    if cx0 >= cx1 or cy0 >= cy1:
        return
    p = patch[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    reg = ink[cy0:cy1, cx0:cx1]
    ink[cy0:cy1, cx0:cx1] = 1 - (1 - reg) * (1 - p)


def render_pages(profile: ProfileData, text: str, opt: RenderOptions | None = None,
                 only: int | None = None) -> tuple[list[Image.Image], Report]:
    """Renderiza todas las páginas, o solo la de índice `only` (misma semilla = mismo resultado)."""
    opt = opt or RenderOptions()
    if opt.paper not in P.PAPER_KINDS:
        raise ValueError(f"Tipo de papel desconocido: {opt.paper}")
    comp = _Composer(profile, opt)
    line_px = P.line_spacing_px(opt.paper, opt.line_mm)
    top_px, left_px = P.mm(opt.top_mm), P.mm(opt.left_mm)
    avail_w = L.PAGE_W - left_px - P.mm(opt.right_mm)
    lines_per_page = max(1, int((L.PAGE_H - top_px - P.mm(opt.bottom_mm)) // line_px))
    ink_rgb = np.array(resolve_ink(opt.ink, profile), np.float32)
    stroke = profile.stroke_width()

    lines = comp.layout(text, avail_w)
    while lines and lines[-1].blank:
        lines.pop()
    if not lines:
        raise ValueError("No hay texto para escribir.")

    nat = comp.nat
    total = math.ceil(len(lines) / lines_per_page)
    if only is not None and not 0 <= only < total:
        raise ValueError("Esa página no existe.")
    pages: list[Image.Image] = []
    for page_idx in range(total):
        if only is not None and page_idx != only:
            continue
        # cada página tiene su propio generador: se puede renderizar sola y sale igual
        rng = np.random.default_rng([comp.seed, page_idx + 1])
        start = page_idx * lines_per_page
        chunk = lines[start:start + lines_per_page]
        paper = P.make_paper(opt.paper, line_px, top_px, left_px)
        ink = np.zeros((L.PAGE_H, L.PAGE_W), np.float32)
        under = np.zeros((L.PAGE_H, L.PAGE_W), np.uint8)
        for k, line in enumerate(chunk):
            if line.blank or not line.words:
                continue
            base0 = P.baseline_y(top_px, line_px, k) - 0.06 * comp.xh_px
            x_off = left_px + float(np.clip(rng.normal(0, 1.2 * P.mm(1) * nat), -P.mm(3), P.mm(3)))
            amp = 0.05 * comp.xh_px * nat
            lam = 900 + 600 * float(rng.random())
            phi = float(rng.random()) * 2 * math.pi
            slope = float(rng.normal(0, 0.004 * nat))
            end_x = 0.0
            for wx, word in line.words:
                for it in word.items:
                    gx = wx + it.x
                    drift = amp * math.sin(2 * math.pi * gx / lam + phi) + slope * gx
                    g = it.glyph
                    bottom = base0 + drift + it.dy + g.bottom_offset * it.scale
                    cx = x_off + gx - 2 * it.scale + g.w * it.scale / 2
                    cy = bottom - g.h * it.scale / 2
                    _paste(ink, g.alpha, cx, cy, it.scale, it.theta)
                end_x = wx + word.width
            if line.title:
                first = line.words[0][0]
                y = base0 + 0.32 * comp.xh_px * (line.scale / comp.s0)
                n = max(2, int((end_x - first) // 24))
                pts = []
                for i in range(n + 1):
                    gx = first + (end_x - first) * i / n
                    drift = amp * math.sin(2 * math.pi * gx / lam + phi) + slope * gx
                    pts.append([x_off + gx, y + drift + float(rng.normal(0, 0.4 * nat))])
                th = max(1, round(stroke * line.scale * 0.9))
                cv2.polylines(under, [np.round(np.array(pts)).astype(np.int32)], False, 255, th, cv2.LINE_AA)
        ink = 1 - (1 - ink) * (1 - under.astype(np.float32) / 255.0 * 0.92)
        alpha = np.clip(ink * 0.97, 0, 1)
        if opt.realism:
            alpha = cv2.GaussianBlur(alpha, (0, 0), 0.55)
        out = paper * (1 - alpha[..., None] * (1 - ink_rgb / 255.0))
        if opt.realism:
            noise = rng.normal(0, 1.1, (L.PAGE_H, L.PAGE_W, 1)).astype(np.float32)
            yy = np.linspace(-1, 1, L.PAGE_H, dtype=np.float32)[:, None, None]
            out = out + noise - 3.0 * yy ** 2
        pages.append(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB"))
    comp.report.pages = total
    return pages, comp.report
