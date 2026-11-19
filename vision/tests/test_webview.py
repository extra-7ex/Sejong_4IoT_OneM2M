"""브라우저 실시간 화면(webview)과 바닥점 → 화면 투영."""
import threading
import time
import urllib.request

import numpy as np

from vision4iot.calib import Calib
from vision4iot.webview import WebView


def test_no_viewer_means_no_encoding():
    web = WebView(port=0)
    assert not web.wanted
    web.update(np.zeros((48, 64, 3), np.uint8))
    assert web.jpg is None


def test_snapshot_and_stream_serve_jpeg():
    web = WebView(port=0, max_fps=0).start()
    port = web.server.server_port
    stop = threading.Event()

    def feed():
        while not stop.is_set():
            web.update(np.full((48, 64, 3), 128, np.uint8))
            time.sleep(0.02)

    threading.Thread(target=feed, daemon=True).start()
    try:
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode()
        assert "/stream" in page
        snap = urllib.request.urlopen(f"http://127.0.0.1:{port}/snapshot.jpg", timeout=5).read()
        assert snap[:2] == b"\xff\xd8"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/stream", timeout=5) as res:
            assert res.headers["Content-Type"].startswith("multipart/x-mixed-replace")
            assert b"\xff\xd8" in res.read(2000)
    finally:
        stop.set()
        web.stop()


def test_guides_toggle_and_draw():
    from vision4iot.webview import draw_guides
    web = WebView(port=0).start()
    port = web.server.server_port
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/guides/on", timeout=5).read()
        assert web.guides
        urllib.request.urlopen(f"http://127.0.0.1:{port}/guides/off", timeout=5).read()
        assert not web.guides
    finally:
        web.stop()
    frame = np.zeros((480, 640, 3), np.uint8)
    draw_guides(frame)
    assert frame[120].any() and frame[:, 320].any()


def test_to_image_inverts_to_floor():
    H = np.array([[0.01, 0.0, -3.2], [0.0, -0.02, 10.0], [0.0, 0.001, 1.0]])
    cal = Calib(H=H, image_size=(640, 480))
    u, v = 300.0, 400.0
    x, y = cal.to_floor([[u, v]])[0]
    assert np.allclose(cal.to_image(x, y), (u, v), atol=1e-6)
    assert np.allclose(cal.to_image(x, y, (1280, 960)), (2 * u, 2 * v), atol=1e-6)
