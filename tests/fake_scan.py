"""Simula una hoja rellena a mano y fotografiada, para probar el pipeline sin letra real."""
from __future__ import annotations

import io
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from letracrack import layout as L
from letracrack.template import make_template

FONT_PATHS = ["C:/Windows/Fonts/segoepr.ttf", "C:/Windows/Fonts/inkfree.ttf", "DejaVuSans.ttf"]


def _font(size: int):
    for p in FONT_PATHS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def filled_sheet(seed: int = 0, ink=(25, 40, 120)) -> Image.Image:
    rnd = random.Random(seed)
    img = make_template()
    d = ImageDraw.Draw(img)
    for cell in L.cells():
        size = rnd.randint(50, 56)
        font = _font(size)
        # ancla "ls" = left/baseline: la letra se apoya exactamente en la línea guía
        x = cell.x0 + rnd.randint(40, 70)
        y = cell.baseline + rnd.randint(-3, 3)
        d.text((x, y), cell.char, font=font, fill=ink, anchor="ls")
    return img


def photograph(img: Image.Image, seed: int = 0, tilt: float = 4.0) -> bytes:
    """Perspectiva, rotación, sombra, desenfoque, ruido y fondo de mesa; devuelve un JPEG."""
    rnd = np.random.default_rng(seed)
    a = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    h, w = a.shape[:2]
    out_w, out_h = 2400, 3200
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    jitter = rnd.uniform(-70, 70, (4, 2)).astype(np.float32)
    dst = np.float32([[260, 300], [out_w - 250, 330], [out_w - 280, out_h - 300], [230, out_h - 340]]) + jitter
    M = cv2.getPerspectiveTransform(src, dst)
    table = np.full((out_h, out_w, 3), (70, 95, 120), np.uint8)
    warp = cv2.warpPerspective(a, M, (out_w, out_h), flags=cv2.INTER_CUBIC, borderValue=(0, 0, 0))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), M, (out_w, out_h))
    photo = np.where(mask[..., None] > 0, warp, table).astype(np.float32)
    # sombra suave y gradiente de luz
    yy, xx = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
    light = 0.78 + 0.22 * (1 - (xx / out_w) * 0.8) + 0.05 * np.sin(yy / 400)
    photo *= light[..., None]
    rot = cv2.getRotationMatrix2D((out_w / 2, out_h / 2), tilt, 1.0)
    photo = cv2.warpAffine(photo, rot, (out_w, out_h), borderValue=(70, 95, 120))
    photo = cv2.GaussianBlur(photo, (0, 0), 1.2)
    photo += rnd.normal(0, 3.0, photo.shape)
    ok, buf = cv2.imencode(".jpg", np.clip(photo, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 88])
    assert ok
    return io.BytesIO(buf.tobytes()).getvalue()
