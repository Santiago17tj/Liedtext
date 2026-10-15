"""Punto de entrada para Vercel (detecta `app`). En local usa run.py."""
from letracrack.app import create_app

app = create_app()
