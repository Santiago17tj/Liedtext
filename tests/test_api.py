from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_scan import filled_sheet, photograph  # noqa: E402
from test_pipeline import merge  # noqa: E402

from letracrack import app as app_mod  # noqa: E402


@pytest.fixture()
def client():
    return app_mod.create_app().test_client()


def scan(client, seed=0, data=None):
    data = data or photograph(filled_sheet(seed), seed=seed)
    return client.post("/api/scan", data={"file": (io.BytesIO(data), "hoja.jpg")}, content_type="multipart/form-data")


def test_full_flow(client):
    assert client.get("/").status_code == 200
    assert client.get("/app.js").status_code == 200
    assert client.get("/api/template.pdf?sheets=1").data[:4] == b"%PDF"

    profile = {"glyphs": [], "ink_rgb": None}
    for s in range(2):
        r = scan(client, s)
        assert r.status_code == 200 and r.get_json()["found"] >= 90
        merge(profile, r.get_json())

    bad = scan(client, data=b"no soy una imagen")
    assert bad.status_code == 422 and "error" in bad.get_json()

    req = {"profile": profile, "text": "# Hola\nmundo ☃ " + "relleno largo " * 900, "paper": "cuadriculado", "seed": 5, "page": 0}
    r = client.post("/api/render", json=req)
    out = r.get_json()
    assert r.status_code == 200 and out["report"]["missing"] == ["☃"] and out["total"] >= 2
    jpeg = base64.b64decode(out["jpeg"])
    assert jpeg[:2] == b"\xff\xd8"
    assert len(out["jpeg"]) < 3_000_000, "una página debe caber holgada en el límite de 4,5 MB de Vercel"

    r2 = client.post("/api/render", json={**req, "page": 1})
    assert r2.status_code == 200 and r2.get_json()["page"] == 1

    assert client.post("/api/render", json={**req, "page": 99}).status_code == 400
    assert client.post("/api/render", json={**req, "text": "  "}).status_code == 400
    assert client.post("/api/render", json={**req, "profile": {"glyphs": "x"}}).status_code == 400
    assert client.post("/api/render", json={**req, "paper": "otro"}).status_code == 400


def test_nothing_is_written_to_disk(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert scan(client).status_code == 200
    assert list(tmp_path.iterdir()) == []


def test_password_gate(monkeypatch):
    monkeypatch.setenv("LETRACRACK_PASSWORD", "secreto")
    c = app_mod.create_app().test_client()
    assert c.get("/api/session").get_json() == {"protected": True, "authed": False}
    r = scan(c)
    assert r.status_code == 401 and r.get_json()["login"] is True
    assert c.post("/api/render", json={}).status_code == 401
    assert c.post("/api/login", json={"password": "mal"}).status_code == 401
    assert c.get("/api/template.pdf").status_code == 200  # la plantilla es pública
    assert c.post("/api/login", json={"password": "secreto"}).status_code == 200
    assert c.get("/api/session").get_json()["authed"] is True
    assert scan(c).status_code == 200
