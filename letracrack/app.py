"""Servidor de Letracrack. No guarda nada: el perfil de escritura vive en el navegador."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import os
import time
from pathlib import Path

from flask import Flask, Response, jsonify, request, send_from_directory

from . import extract as ex
from . import paper as P
from . import template as T
from .profile import ProfileData, scan_photo
from .render import RenderOptions, render_pages

PUBLIC = Path(__file__).resolve().parent.parent / "public"
AUTH_COOKIE = "lc_auth"
OPEN_API = {"/api/session", "/api/login", "/api/template.pdf"}


def _token(password: str) -> str:
    return hmac.new(password.encode(), b"letracrack-v1", hashlib.sha256).hexdigest()


def create_app() -> Flask:
    # En Vercel los archivos de public/ los sirve la CDN; en local los sirve Flask.
    app = Flask(__name__, static_folder=str(PUBLIC), static_url_path="")
    app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
    password = os.environ.get("LETRACRACK_PASSWORD") or ""

    def authed() -> bool:
        return not password or hmac.compare_digest(request.cookies.get(AUTH_COOKIE, ""), _token(password))

    @app.before_request
    def gate():
        if request.path.startswith("/api/") and request.path not in OPEN_API and not authed():
            return jsonify(error="Escribe la contraseña para continuar.", login=True), 401

    @app.errorhandler(ValueError)
    def _bad(e):
        return jsonify(error=str(e)), 400

    @app.errorhandler(ex.ScanError)
    def _scan(e):
        return jsonify(error=str(e)), 422

    @app.errorhandler(413)
    def _big(_e):
        return jsonify(error="El archivo es demasiado grande (máximo 30 MB)."), 413

    @app.get("/")
    def index():
        return send_from_directory(PUBLIC, "index.html")

    # ---- acceso ----------------------------------------------------------
    @app.get("/api/session")
    def session():
        return jsonify(protected=bool(password), authed=authed())

    @app.post("/api/login")
    def login():
        given = str((request.get_json(silent=True) or {}).get("password", ""))
        if not password or not hmac.compare_digest(_token(given), _token(password)):
            time.sleep(0.7)
            return jsonify(error="Contraseña incorrecta."), 401
        resp = jsonify(ok=True)
        secure = request.is_secure or request.headers.get("x-forwarded-proto") == "https"
        resp.set_cookie(AUTH_COOKIE, _token(password), max_age=60 * 60 * 24 * 30, httponly=True,
                        samesite="Lax", secure=secure)
        return resp

    # ---- plantilla -------------------------------------------------------
    @app.get("/api/template.pdf")
    def template_pdf():
        sheets = min(max(int(request.args.get("sheets", 3)), 1), 6)
        return Response(T.template_pdf_bytes(sheets), mimetype="application/pdf",
                        headers={"Content-Disposition": "inline; filename=plantilla-letracrack.pdf",
                                 "Cache-Control": "public, max-age=86400"})

    # ---- procesamiento (sin estado) -----------------------------------------
    @app.post("/api/scan")
    def scan():
        f = request.files.get("file")
        if f is None:
            raise ValueError("No se recibió ninguna foto.")
        return jsonify(scan_photo(f.read()))

    @app.post("/api/render")
    def render():
        d = request.get_json(silent=True) or {}
        profile = ProfileData.from_json(d.get("profile"))
        text = str(d.get("text", ""))
        if not text.strip():
            raise ValueError("Escribe o pega el texto que quieres pasar a mano.")
        if len(text) > 60000:
            raise ValueError("El texto es demasiado largo (máximo 60 000 caracteres).")
        paper = d.get("paper", "rayado")
        if paper not in P.PAPER_KINDS:
            raise ValueError("Tipo de papel no válido.")

        def num(key, lo, hi, default=None):
            v = d.get(key)
            if v in (None, ""):
                return default
            return min(max(float(v), lo), hi)

        opt = RenderOptions(
            paper=paper,
            size_mm=num("size_mm", 1.5, 8.0),
            line_mm=num("line_mm", 4.0, 20.0),
            spacing=num("spacing", -0.1, 0.5, 0.10),
            naturalness=num("naturalness", 0.0, 2.5, 1.0),
            ink=str(d.get("ink", "profile")),
            seed=int(num("seed", 0, 2**31 - 1, 0)),
        )
        page = int(num("page", 0, 500, 0))
        pages, rep = render_pages(profile, text, opt, only=page)
        buf = io.BytesIO()
        pages[0].save(buf, "JPEG", quality=90, optimize=True, subsampling=0, dpi=(200, 200))
        return jsonify(
            page=page, total=rep.pages, width=pages[0].width, height=pages[0].height,
            jpeg=base64.b64encode(buf.getvalue()).decode("ascii"),
            report={"chars": rep.chars, "missing": rep.missing, "substituted": rep.substituted},
        )

    return app
