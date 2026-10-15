"""Geometría de la plantilla de captura (todo en píxeles a 200 DPI, hoja A4)."""
from __future__ import annotations

from dataclasses import dataclass

DPI = 200
PX_PER_MM = DPI / 25.4
PAGE_W, PAGE_H = 1654, 2339  # A4 a 200 DPI

LOWER = "abcdefghijklmnopqrstuvwxyz"
UPPER = LOWER.upper()
DIGITS = "0123456789"
ACCENTS = "ñÑáéíóúÁÉÍÓÚüÜ"
PUNCT = ".,;:¿?¡!()-\"'/%+=°&@"
CHARSET = LOWER + UPPER + ACCENTS + DIGITS + PUNCT  # 96 caracteres

COLS, ROWS = 8, 12
CELL_W, CELL_H = 180, 160
LABEL_H = 24  # franja superior con la etiqueta impresa (fuera del recuadro de escritura)
GRID_X0 = (PAGE_W - COLS * CELL_W) // 2
GRID_Y0 = 250
BOX_H = CELL_H - LABEL_H
BASELINE_FRAC = 0.66  # posición de la línea guía dentro del recuadro de escritura

# Marcas de esquina (cuadrados negros). La superior izquierda es más grande: da la orientación.
MARKER_SMALL = 56
MARKER_BIG = 84
MARKER_MARGIN = 40

assert len(CHARSET) == COLS * ROWS, len(CHARSET)
assert len(set(CHARSET)) == len(CHARSET)


@dataclass(frozen=True)
class Cell:
    char: str
    x0: int  # recuadro de escritura (sin la franja de la etiqueta)
    y0: int
    x1: int
    y1: int
    baseline: int  # y absoluta de la línea guía


def cells() -> list[Cell]:
    out = []
    for i, ch in enumerate(CHARSET):
        r, c = divmod(i, COLS)
        x0 = GRID_X0 + c * CELL_W
        y0 = GRID_Y0 + r * CELL_H + LABEL_H
        out.append(Cell(ch, x0, y0, x0 + CELL_W, y0 + BOX_H, y0 + round(BOX_H * BASELINE_FRAC)))
    return out


def marker_centers() -> list[tuple[float, float]]:
    """Centros de las marcas en orden TL, TR, BR, BL."""
    m = MARKER_MARGIN
    big, small = MARKER_BIG, MARKER_SMALL
    return [
        (m + big / 2, m + big / 2),
        (PAGE_W - m - small / 2, m + small / 2),
        (PAGE_W - m - small / 2, PAGE_H - m - small / 2),
        (m + small / 2, PAGE_H - m - small / 2),
    ]


def marker_rects() -> list[tuple[int, int, int, int]]:
    m = MARKER_MARGIN
    big, small = MARKER_BIG, MARKER_SMALL
    return [
        (m, m, m + big, m + big),
        (PAGE_W - m - small, m, PAGE_W - m, m + small),
        (PAGE_W - m - small, PAGE_H - m - small, PAGE_W - m, PAGE_H - m),
        (m, PAGE_H - m - small, m + small, PAGE_H - m),
    ]
