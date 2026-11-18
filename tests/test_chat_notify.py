import os, tempfile, unittest
from pathlib import Path
from unittest import mock

import numpy as np

from app import notify
from app.chat_events import detect_chat_spikes


def _chat(seed=1):
    rnd = np.random.default_rng(seed)
    base = list(np.sort(rnd.uniform(0, 600, 150)))          # ~1 mensaje cada 4 s durante 10 min
    burst = list(np.sort(rnd.uniform(300, 308, 60)))          # ráfaga de 60 mensajes en 8 s
    return base + burst


class ChatSpikes(unittest.TestCase):
    def test_encuentra_la_rafaga(self):
        hits = detect_chat_spikes(_chat())
        self.assertEqual(len(hits), 1)
        self.assertTrue(290 <= hits[0].t <= 305, hits[0].t)   # un poco antes de la ráfaga (retardo del chat)
        self.assertEqual(hits[0].kind, "chat")

    def test_chat_tranquilo_no_dispara(self):
        for seed in range(2, 12):  # el azar normal del chat nunca debe parecer una ráfaga
            rnd = np.random.default_rng(seed)
            self.assertEqual(detect_chat_spikes(list(np.sort(rnd.uniform(0, 600, 150)))), [], seed)

    def test_pocos_mensajes(self):
        self.assertEqual(detect_chat_spikes([1.0, 2.0]), [])

    def test_sensibilidad_alta_encuentra_mas(self):
        t = _chat() + list(np.sort(np.random.default_rng(3).uniform(450, 460, 20)))
        self.assertGreaterEqual(len(detect_chat_spikes(t, 1.0)), len(detect_chat_spikes(t, 0.0)))


class Notify(unittest.TestCase):
    def setUp(self):
        self.f = Path(tempfile.mkdtemp()) / "c.mp4"
        self.f.write_bytes(b"x" * 100)
        for k in ("CLIPRADAR_TELEGRAM_TOKEN", "CLIPRADAR_TELEGRAM_CHAT_ID", "CLIPRADAR_DISCORD_WEBHOOK"):
            os.environ.pop(k, None)

    def test_sin_configurar_no_hace_nada(self):
        self.assertFalse(notify.configured())
        with mock.patch.object(notify, "_post") as p:
            notify.send_async(self.f, {"kinds": ["risas"]})
            p.assert_not_called()

    def test_telegram_envia_video(self):
        os.environ["CLIPRADAR_TELEGRAM_TOKEN"], os.environ["CLIPRADAR_TELEGRAM_CHAT_ID"] = "T", "9"
        with mock.patch.object(notify, "_post", return_value=200) as p:
            self.assertEqual(notify.send_clip(self.f, "hola"), ["telegram: ok"])
            self.assertIn("/botT/sendVideo", p.call_args[0][0])
            self.assertIn(b'name="chat_id"', p.call_args[0][1])
            self.assertIn(b"x" * 100, p.call_args[0][1])

    def test_error_no_rompe(self):
        os.environ["CLIPRADAR_DISCORD_WEBHOOK"] = "https://example.invalid/h"
        with mock.patch.object(notify, "_post", side_effect=OSError("red")):
            self.assertEqual(notify.send_clip(self.f, "x"), ["discord: error OSError"])

    def test_grande_manda_solo_texto(self):
        os.environ["CLIPRADAR_TELEGRAM_TOKEN"], os.environ["CLIPRADAR_TELEGRAM_CHAT_ID"] = "T", "9"
        with mock.patch.object(notify, "TG_LIMIT", 10), mock.patch.object(notify, "_post", return_value=200) as p:
            notify.send_clip(self.f, "hola")
            self.assertIn("/sendMessage", p.call_args[0][0])

    def test_clip_manual_no_se_envia(self):
        os.environ["CLIPRADAR_DISCORD_WEBHOOK"] = "https://example.invalid/h"
        with mock.patch("threading.Thread") as th:
            notify.send_async(self.f, {"kinds": ["manual"]})
            th.assert_not_called()


if __name__ == "__main__":
    unittest.main()
