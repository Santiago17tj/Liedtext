"""Genera la hoja plantilla que el usuario imprime, rellena a mano y fotografía."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import layout as L

GUIDE = (205, 218, 235)  # azul muy claro: se imprime tenue y se elimina al extraer
GUIDE_STRONG = (150, 175, 210)

_FONT_CANDIDATES = [
    "arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def make_template(sheet: int = 1, total: int = 3) -> Image.Image:
    img = Image.new("RGB", (L.PAGE_W, L.PAGE_H), "white")
    d = ImageDraw.Draw(img)

    for x0, y0, x1, y1 in L.marker_rects():
        d.rectangle([x0, y0, x1 - 1, y1 - 1], fill="black")

    d.text((L.GRID_X0, 120), "LETRACRACK · Plantilla de escritura", font=load_font(34), fill=(30, 30, 30))
    d.text((L.PAGE_W - L.GRID_X0, 124), f"Hoja {sheet} de {total}", font=load_font(28), fill=(30, 30, 30), anchor="ra")
    small = load_font(21)
    d.text((L.GRID_X0, 172), "Escribe cada carácter en su recuadro, apoyado en la línea guía, con tu letra natural y tamaño normal.",
           font=small, fill=(70, 70, 70))
    d.text((L.GRID_X0, 200), "No toques los bordes. Usa el mismo bolígrafo que usas en tus cuadernos. Fotografía la hoja entera, con luz pareja.",
           font=small, fill=(70, 70, 70))

    label_font = load_font(20)
    for cell in L.cells():
        d.rectangle([cell.x0, cell.y0, cell.x1 - 1, cell.y1 - 1], outline=GUIDE, width=2)
        d.line([cell.x0 + 6, cell.baseline, cell.x1 - 7, cell.baseline], fill=GUIDE_STRONG, width=1)
        d.text((cell.x0 + 6, cell.y0 - L.LABEL_H + 1), cell.char, font=label_font, fill=(40, 40, 40))
    return img


def template_png_bytes(sheet: int = 1, total: int = 3) -> bytes:
    buf = io.BytesIO()
    make_template(sheet, total).save(buf, "PNG", dpi=(L.DPI, L.DPI))
    return buf.getvalue()


def template_pdf_bytes(sheets: int = 3) -> bytes:
    pages = [make_template(i + 1, sheets) for i in range(sheets)]
    buf = io.BytesIO()
    pages[0].save(buf, "PDF", resolution=L.DPI, save_all=True, append_images=pages[1:])
    return buf.getvalue()


def save_template(path: str | Path, sheet: int = 1, total: int = 3) -> None:
    make_template(sheet, total).save(path, dpi=(L.DPI, L.DPI))
