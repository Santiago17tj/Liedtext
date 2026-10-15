"""De una foto de la plantilla rellena a glifos individuales."""
from __future__ import annotations

import itertools
from dataclasses import dataclass

import cv2
import numpy as np

from . import layout as L

INSET = 7  # px recortados dentro del recuadro para no leer el borde impreso
MIN_COMPONENT_AREA = 14
ALPHA_HI, ALPHA_LO = 0.82, 0.45  # sobre la imagen normalizada: >HI = papel, <LO = tinta plena


class ScanError(Exception):
    """La foto no se pudo interpretar; el mensaje es apto para mostrar al usuario."""


@dataclass
class ExtractedGlyph:
    char: str
    alpha: np.ndarray  # uint8, 0 = papel, 255 = tinta
    bottom_offset: int  # píxeles del borde inferior del glifo por debajo de la línea guía (negativo = encima)
    touches_border: bool


@dataclass
class ScanResult:
    glyphs: list[ExtractedGlyph]
    missing: list[str]
    ink_rgb: tuple[int, int, int] | None
    warped: np.ndarray


def decode_image(data: bytes) -> np.ndarray:
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ScanError("No se pudo leer la imagen (formato no soportado).")
    return img


def normalize_background(gray: np.ndarray) -> np.ndarray:
    """Divide por el fondo estimado: papel ≈ 1.0 aunque haya sombras o gradientes."""
    k = max(15, (min(gray.shape) // 60) | 1)
    bg = cv2.dilate(gray, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 2)
    return np.clip(gray.astype(np.float32) / np.maximum(bg.astype(np.float32), 1.0), 0, 1.2)


def _order_cyclic(pts: np.ndarray) -> np.ndarray:
    c = pts.mean(axis=0)
    ang = np.arctan2(pts[:, 1] - c[1], pts[:, 0] - c[0])
    return pts[np.argsort(ang)]  # en coordenadas de imagen (y hacia abajo): TL, TR, BR, BL


def find_markers(img: np.ndarray) -> np.ndarray:
    """Devuelve los 4 centros de marcas en orden TL, TR, BR, BL (según la plantilla)."""
    h, w = img.shape[:2]
    scale = 1600 / max(h, w) if max(h, w) > 1600 else 1.0
    small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale != 1.0 else img
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    norm = normalize_background(gray)
    mask = (norm < 0.45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_area = small.shape[0] * small.shape[1]
    cands = []
    for c in contours:
        area = cv2.contourArea(c)
        if not (0.0001 * img_area <= area <= 0.01 * img_area):
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        if not (0.55 <= bw / bh <= 1.8):
            continue
        hull = cv2.contourArea(cv2.convexHull(c))
        if hull <= 0 or area / hull < 0.9:
            continue
        rect = cv2.minAreaRect(c)
        rw, rh = rect[1]
        if rw * rh <= 0 or area / (rw * rh) < 0.8:
            continue
        m = cv2.moments(c)
        cands.append((m["m10"] / m["m00"], m["m01"] / m["m00"], area))

    if len(cands) < 4:
        raise ScanError(
            f"Solo encontré {len(cands)} de las 4 marcas negras de las esquinas. "
            "Fotografía la hoja completa, con las cuatro esquinas visibles y buena luz."
        )
    if len(cands) > 12:
        cands = sorted(cands, key=lambda t: -t[2])[:12]

    best, best_area = None, -1.0
    for combo in itertools.combinations(cands, 4):
        pts = _order_cyclic(np.array([[c[0], c[1]] for c in combo], dtype=np.float32))
        quad = abs(cv2.contourArea(pts))
        areas = [c[2] for c in combo]
        # las tres marcas pequeñas deben ser parecidas entre sí
        srt = sorted(areas)
        if srt[2] > 0 and srt[0] < 0.35 * srt[2]:
            continue
        if quad > best_area:
            best, best_area = combo, quad
    if best is None:
        raise ScanError("Las marcas detectadas no forman un rectángulo coherente. Prueba con otra foto.")

    pts = np.array([[c[0], c[1]] for c in best], dtype=np.float32)
    areas = np.array([c[2] for c in best])
    order = np.argsort(np.arctan2(pts[:, 1] - pts[:, 1].mean(), pts[:, 0] - pts[:, 0].mean()))
    pts, areas = pts[order], areas[order]
    srt = np.sort(areas)
    if srt[-1] > 1.35 * srt[-2]:
        k = int(np.argmax(areas))  # la marca grande es la esquina superior izquierda
    else:
        k = int(np.argmin(pts.sum(axis=1)))  # sin marca distintiva clara: suponer foto derecha
    pts = np.roll(pts, -k, axis=0)
    return pts / scale


def rectify(img: np.ndarray) -> np.ndarray:
    src = find_markers(img)
    dst = np.array(L.marker_centers(), dtype=np.float32)
    H = cv2.getPerspectiveTransform(src.astype(np.float32), dst)
    return cv2.warpPerspective(img, H, (L.PAGE_W, L.PAGE_H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def extract_glyphs(img: np.ndarray) -> ScanResult:
    warped = rectify(img)
    gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    norm = normalize_background(gray)
    alpha_full = np.clip((ALPHA_HI - norm) / (ALPHA_HI - ALPHA_LO), 0, 1)
    mask_full = (norm < 0.66).astype(np.uint8)

    glyphs: list[ExtractedGlyph] = []
    missing: list[str] = []
    ink_samples: list[np.ndarray] = []
    for cell in L.cells():
        x0, y0, x1, y1 = cell.x0 + INSET, cell.y0 + INSET, cell.x1 - INSET, cell.y1 - INSET
        sub_mask = mask_full[y0:y1, x0:x1]
        n, lab, stats, _ = cv2.connectedComponentsWithStats(sub_mask, connectivity=8)
        keep = np.zeros_like(sub_mask)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] >= MIN_COMPONENT_AREA:
                keep[lab == i] = 1
        if keep.sum() == 0:
            missing.append(cell.char)
            continue
        ys, xs = np.where(keep)
        bx0, bx1, by0, by1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        grown = cv2.dilate(keep, np.ones((5, 5), np.uint8))
        alpha = (alpha_full[y0:y1, x0:x1] * grown * 255).astype(np.uint8)
        pad = 2
        cx0, cy0 = max(bx0 - pad, 0), max(by0 - pad, 0)
        cx1, cy1 = min(bx1 + pad, alpha.shape[1]), min(by1 + pad, alpha.shape[0])
        crop = alpha[cy0:cy1, cx0:cx1]
        touches = bx0 <= 1 or by0 <= 1 or bx1 >= keep.shape[1] - 1 or by1 >= keep.shape[0] - 1
        # bottom_offset se mide hasta el borde inferior del recorte (incluye el padding)
        bottom_offset = int(y0 + cy1 - cell.baseline)
        glyphs.append(ExtractedGlyph(cell.char, crop, bottom_offset, touches))

        dark = (keep > 0) & (alpha_full[y0:y1, x0:x1] > 0.9)
        if dark.any():
            ink_samples.append(warped[y0:y1, x0:x1][dark])

    ink_rgb = None
    if ink_samples:
        px = np.concatenate(ink_samples)  # BGR
        med = np.median(px, axis=0)
        ink_rgb = (int(med[2]), int(med[1]), int(med[0]))
    return ScanResult(glyphs, missing, ink_rgb, warped)


def estimate_stroke_width(alpha: np.ndarray) -> float:
    binary = (alpha > 128).astype(np.uint8)
    if binary.sum() == 0:
        return 2.0
    dt = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    vals = dt[binary > 0]
    return float(max(1.5, 4.0 * vals.mean()))


def sheet_sanity(result: ScanResult) -> list[str]:
    warnings = []
    found = len(result.glyphs)
    if found < 0.5 * len(L.CHARSET):
        warnings.append(f"Solo se detectó escritura en {found} de {len(L.CHARSET)} recuadros.")
    touching = [g.char for g in result.glyphs if g.touches_border]
    if touching:
        warnings.append("Tocan el borde del recuadro (pueden estar cortados): " + " ".join(touching))
    return warnings
