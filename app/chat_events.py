"""Señal de chat: momentos en que el chat se llena de mensajes de golpe.

Es la señal que más usan los clippers de directos: cuando pasa algo, el chat explota unos
segundos después. Se combina con las señales de audio y de palabras en `moments.py`.

* `detect_chat_spikes` es una función pura (solo recibe los tiempos de los mensajes).
* `fetch_chat_times` descarga el chat de un video/directo grabado con `chat-downloader`
  (YouTube y Twitch). Es opcional: si no está instalado o el sitio no lo permite, devuelve [].
"""
from __future__ import annotations

import time

import numpy as np

from .audio_events import Hit

CHAT_LAG = 3.0  # el chat reacciona ~3 s después del suceso: se resta para apuntar al momento real


def detect_chat_spikes(
    times: list[float],
    sensitivity: float = 0.5,
    window: float = 10.0,
    min_msgs: int = 10,
    min_gap: float = 20.0,
    baseline_s: float = 180.0,
) -> list[Hit]:
    """Ráfagas de mensajes muy por encima del ritmo normal del chat.

    `sensitivity` 0..1: más alto = dispara con ráfagas más pequeñas.
    Devuelve Hit(kind="chat") con t = inicio de la ráfaga menos el retardo típico del chat.
    """
    if len(times) < min_msgs:
        return []
    ts = np.sort(np.asarray(times, dtype=float))
    ratio = 4.0 - 2.5 * float(np.clip(sensitivity, 0, 1))  # 4x (poco sensible) .. 1.5x (muy sensible)
    z = 6.0 - 3.0 * float(np.clip(sensitivity, 0, 1))  # desviaciones por encima del ritmo normal (azar de Poisson)
    step = 2.0
    starts = np.arange(max(0.0, ts[0] - window), ts[-1] + step, step)
    counts = np.searchsorted(ts, starts + window) - np.searchsorted(ts, starts)
    n_base = max(3, int(baseline_s / step))
    cand: list[tuple[float, float, int]] = []  # (inicio, puntuación, mensajes)
    for i, c in enumerate(counts):
        prev = counts[max(0, i - n_base): max(0, i - int(window / step))]
        base = float(np.median(prev)) if len(prev) >= 3 else float(np.median(counts))
        base = max(base, 1.0)
        if c >= max(min_msgs, ratio * base, base + z * base ** 0.5):
            cand.append((float(starts[i]), min(1.0, (c / base) / (ratio * 3)), int(c)))
    hits: list[Hit] = []
    for start, score, c in sorted(cand, key=lambda x: -x[1]):  # los más fuertes primero
        t = max(0.0, start - CHAT_LAG)
        if all(abs(t - h.t) >= min_gap for h in hits):
            hits.append(Hit(t, "chat", max(0.3, score), f"{c} mensajes en {window:.0f}s"))
    return sorted(hits, key=lambda h: h.t)


def fetch_chat_times(url: str, max_messages: int = 200_000, max_seconds: float = 180.0) -> tuple[list[float], str]:
    """Tiempos (s desde el inicio del video) de los mensajes del chat. Devuelve (tiempos, motivo_si_falla)."""
    try:
        from chat_downloader import ChatDownloader
    except ImportError:
        return [], "chat-downloader no está instalado (pip install chat-downloader)"
    times: list[float] = []
    deadline = time.monotonic() + max_seconds
    try:
        chat = ChatDownloader().get_chat(url, message_types=["text_message"], max_messages=max_messages,
                                         inactivity_timeout=60)
        for msg in chat:
            t = msg.get("time_in_seconds")
            if isinstance(t, (int, float)) and t >= 0:
                times.append(float(t))
            if time.monotonic() > deadline:
                break
    except Exception as exc:  # sitio no soportado, chat desactivado, sin repetición, red…
        if not times:
            return [], f"{type(exc).__name__}: {str(exc)[:140]}"
    return times, ""
