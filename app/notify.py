"""Envía cada clip terminado a tu Telegram o Discord para que solo tengas que publicarlo.

Se activa con variables de entorno (en `.env`); sin ellas no hace nada:
  CLIPRADAR_TELEGRAM_TOKEN + CLIPRADAR_TELEGRAM_CHAT_ID   (bot de Telegram, vídeos hasta 50 MB)
  CLIPRADAR_DISCORD_WEBHOOK                                (webhook de Discord, hasta ~25 MB)
Nunca bloquea ni rompe el clipeo: los errores se ignoran y se escriben en el log.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
import uuid
from pathlib import Path

TG_LIMIT = 50 * 1024 * 1024
DISCORD_LIMIT = 24 * 1024 * 1024


def configured() -> bool:
    return bool(os.environ.get("CLIPRADAR_DISCORD_WEBHOOK") or
                (os.environ.get("CLIPRADAR_TELEGRAM_TOKEN") and os.environ.get("CLIPRADAR_TELEGRAM_CHAT_ID")))


def caption_for(clip: dict, job_url: str = "") -> str:
    kinds = ", ".join(clip.get("kinds", []))
    parts = [f"{clip.get('emoji', '')} {clip.get('title', '')}".strip(),
             f"Señales: {kinds} · puntaje {clip.get('viral_score', '?')}",
             f"Dura {clip.get('end', 0) - clip.get('start', 0):.0f}s"]
    if job_url:
        parts.append(f"Origen: {job_url}")
    return "\n".join(parts)[:1000]


def _multipart(fields: dict[str, str], file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = b""
    for k, v in fields.items():
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{path.name}"\r\n'
            f'Content-Type: video/mp4\r\n\r\n').encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def _post(url: str, body: bytes, ctype: str) -> int:
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status


def send_clip(path: Path, caption: str) -> list[str]:
    """Envía el clip a los destinos configurados. Devuelve lista de resultados ('telegram: ok', …)."""
    results: list[str] = []
    size = path.stat().st_size if path.exists() else 0
    token, chat = os.environ.get("CLIPRADAR_TELEGRAM_TOKEN"), os.environ.get("CLIPRADAR_TELEGRAM_CHAT_ID")
    if token and chat:
        try:
            if size and size <= TG_LIMIT:
                body, ct = _multipart({"chat_id": chat, "caption": caption, "supports_streaming": "true"}, "video", path)
                _post(f"https://api.telegram.org/bot{token}/sendVideo", body, ct)
            else:
                data = json.dumps({"chat_id": chat, "text": caption + "\n(El vídeo pesa más de 50 MB: descárgalo desde ClipRadar)"}).encode()
                _post(f"https://api.telegram.org/bot{token}/sendMessage", data, "application/json")
            results.append("telegram: ok")
        except Exception as exc:
            results.append(f"telegram: error {type(exc).__name__}")
    hook = os.environ.get("CLIPRADAR_DISCORD_WEBHOOK")
    if hook:
        try:
            if size and size <= DISCORD_LIMIT:
                body, ct = _multipart({"payload_json": json.dumps({"content": caption[:1900]})}, "file", path)
                _post(hook, body, ct)
            else:
                _post(hook, json.dumps({"content": caption[:1900] + "\n(Vídeo demasiado grande: descárgalo desde ClipRadar)"}).encode(),
                      "application/json")
            results.append("discord: ok")
        except Exception as exc:
            results.append(f"discord: error {type(exc).__name__}")
    return results


def send_async(path: Path, clip: dict, job_url: str = "") -> None:
    """Lanza el envío en segundo plano si hay destinos configurados y el clip no es manual."""
    if not configured() or clip.get("kinds") == ["manual"]:
        return
    threading.Thread(target=lambda: send_clip(path, caption_for(clip, job_url)), daemon=True).start()
