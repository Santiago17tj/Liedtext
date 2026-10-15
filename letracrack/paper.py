"""Fondos de papel: rayado, cuadriculado y blanco."""
from __future__ import annotations

import numpy as np

from . import layout as L

PAPER_KINDS = ("rayado", "cuadriculado", "blanco")
RULE_COLOR = (150, 190, 232)
GRID_COLOR = (178, 210, 238)
MARGIN_COLOR = (228, 120, 125)


def mm(v: float) -> float:
    return v * L.PX_PER_MM


def line_spacing_px(kind: str, line_mm: float | None) -> float:
    if kind == "cuadriculado":
        n = max(1, round((line_mm or 5.0) / 5.0))
        return mm(5.0) * n
    return mm(line_mm or 8.0)


def baseline_y(top_px: float, line_px: float, k: int) -> float:
    """y de la k-ésima línea de escritura (k = 0 es la primera)."""
    return top_px + (k + 1) * line_px


def make_paper(kind: str, line_px: float, top_px: float, left_px: float) -> np.ndarray:
    img = np.empty((L.PAGE_H, L.PAGE_W, 3), np.float32)
    img[:] = (253, 252, 249) if kind != "blanco" else (254, 254, 252)

    if kind == "rayado":
        k0 = -int(top_px // line_px) - 1
        k = k0
        while True:
            y = round(top_px + k * line_px)
            k += 1
            if y < mm(12):
                continue
            if y > L.PAGE_H - mm(8):
                break
            img[y:y + 2, :, :] = RULE_COLOR
        mx = round(left_px - mm(3))
        img[:, mx:mx + 2, :] = MARGIN_COLOR
        img[:, mx + 5:mx + 7, :] = MARGIN_COLOR
    elif kind == "cuadriculado":
        g = mm(5.0)
        k = -int(top_px // g) - 1
        while True:
            y = round(top_px + k * g)
            k += 1
            if y < mm(8):
                continue
            if y > L.PAGE_H - mm(6):
                break
            img[y:y + 1, :, :] = GRID_COLOR
        x = left_px % g
        while x < L.PAGE_W:
            xi = round(x)
            img[:, xi:xi + 1, :] = GRID_COLOR
            x += g
    return img
