"""Arranque: python -m app"""
import os
import threading
import webbrowser

import uvicorn

from .config import HOST, PORT

if __name__ == "__main__":
    url = f"http://{'localhost' if HOST in ('0.0.0.0', '127.0.0.1') else HOST}:{PORT}"
    print("\n" + "=" * 58)
    print("  🚀 ClipRadar Studio está listo y corriendo localmente")
    print(f"  🌐 Abre tu navegador en: {url}")
    print("  🔑 Acceso Maestro: admin@clipradar.com / admin123")
    print("  💻 Todo el procesamiento corre 100% en esta máquina")
    print("=" * 58 + "\n")
    if os.environ.get("CLIPRADAR_NO_BROWSER") != "1":
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("app.server:app", host=HOST, port=PORT, log_level="warning")
