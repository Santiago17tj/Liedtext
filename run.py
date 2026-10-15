"""Arranca Letracrack en http://127.0.0.1:8765"""
import threading
import webbrowser

from letracrack.app import create_app

HOST, PORT = "127.0.0.1", 8765

if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    create_app().run(host=HOST, port=PORT, debug=False)
