from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_scan import filled_sheet, photograph  # noqa: E402

from letracrack import extract as ex  # noqa: E402
from letracrack import layout as L  # noqa: E402
from letracrack.profile import ProfileData, scan_photo  # noqa: E402
from letracrack.render import RenderOptions, render_pages  # noqa: E402

OUT = Path(__file__).resolve().parent / "_out"


def merge(profile: dict, scan: dict) -> dict:
    """Lo mismo que hace el navegador al añadir una hoja al perfil."""
    counts: dict[str, int] = {}
    for g in profile["glyphs"]:
        counts[g["char"]] = counts.get(g["char"], 0) + 1
    for g in scan["glyphs"]:
        profile["glyphs"].append({"char": g["char"], "variant": counts.get(g["char"], 0),
                                  "bottom_offset": g["bottom_offset"], "png": g["png"]})
        counts[g["char"]] = counts.get(g["char"], 0) + 1
    profile["ink_rgb"] = scan["ink_rgb"]
    return profile


@pytest.fixture(scope="module")
def profile_json():
    p = {"glyphs": [], "ink_rgb": None}
    for seed in range(3):
        scan = scan_photo(photograph(filled_sheet(seed), seed=seed, tilt=[4, -3, 178][seed]))
        assert scan["found"] >= 90, scan["missing"]
        merge(p, scan)
    return p


@pytest.fixture(scope="module")
def profile(profile_json):
    return ProfileData.from_json(profile_json)


def test_markers_and_orientation():
    pts = ex.find_markers(ex.decode_image(photograph(filled_sheet(0), seed=1, tilt=178)))
    assert pts.shape == (4, 2)


def test_missing_markers_gives_friendly_error():
    blank = cv2.imencode(".jpg", np.full((800, 600, 3), 200, np.uint8))[1].tobytes()
    with pytest.raises(ex.ScanError):
        ex.extract_glyphs(ex.decode_image(blank))


def test_profile_loading(profile):
    g = profile.glyphs()
    assert len(g) >= 90 and all(len(v) == 3 for v in g.values())
    assert 20 < profile.xheight() < 60
    assert profile.ink_rgb is not None


@pytest.mark.parametrize("bad", [
    None, {}, {"glyphs": "x"},
    {"glyphs": [{"char": "ab", "png": "AA==", "bottom_offset": 0}]},
    {"glyphs": [{"char": "a", "png": "no-base64!!", "bottom_offset": 0}]},
    {"glyphs": [{"char": "a", "png": "AA==", "bottom_offset": 0}]},
    {"glyphs": [], "ink_rgb": [1, 2]},
])
def test_invalid_profile_rejected(bad):
    with pytest.raises(ValueError):
        ProfileData.from_json(bad)


def test_render_pages(profile):
    text = ("# Taller de categorización\n\nLa categorización permite organizar la información y relacionarla con "
            "conocimientos previos. ¿Qué ocurre después? ¡Mira! (1) año 2024, ñandú.\n- Primer punto de la lista "
            "con un texto largo que debería partirse en varias líneas para comprobar la sangría francesa.\n"
            "- Segundo punto\n\n" + "Texto de relleno para forzar una segunda página. " * 160)
    for kind in ("rayado", "cuadriculado", "blanco"):
        pages, rep = render_pages(profile, text, RenderOptions(paper=kind, seed=7))
        assert rep.pages >= 2 and len(pages) == rep.pages and not rep.missing, rep
        assert pages[0].size == (L.PAGE_W, L.PAGE_H)
        OUT.mkdir(exist_ok=True)
        pages[0].save(OUT / f"{kind}.jpg", quality=90)


def test_single_page_matches_full_render(profile):
    text = "Texto de relleno para forzar varias páginas. " * 200
    opt = RenderOptions(seed=11)
    full, rep = render_pages(profile, text, opt)
    assert rep.pages >= 2
    for i in range(rep.pages):
        one, _ = render_pages(profile, text, opt, only=i)
        assert len(one) == 1 and one[0].tobytes() == full[i].tobytes()
    with pytest.raises(ValueError):
        render_pages(profile, text, opt, only=rep.pages)


def test_unknown_character_is_reported(profile):
    _, rep = render_pages(profile, "hola ☃ mundo", RenderOptions(seed=1))
    assert "☃" in rep.missing


def test_deterministic_with_seed(profile):
    a, _ = render_pages(profile, "hola mundo", RenderOptions(seed=3))
    b, _ = render_pages(profile, "hola mundo", RenderOptions(seed=3))
    assert a[0].tobytes() == b[0].tobytes()
