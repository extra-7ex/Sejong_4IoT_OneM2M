"""브라우저 디버그 화면 (MJPEG). 화면 없는 Pi에서 VisionAI가 보는 화면(사람 뼈대·자세·레이더 표적)을 실시간으로 본다.

    http://<Pi IP>:8090/              실시간 화면
    http://<Pi IP>:8090/snapshot.jpg  지금 한 장

볼 사람이 없으면 JPEG을 만들지 않아 CPU를 쓰지 않는다. 보내는 속도는 max_fps로 제한한다.
"""
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VisionAI 실시간 화면</title>
<body style="margin:0;background:#111;color:#ccc;font:14px system-ui,sans-serif;text-align:center">
<p style="margin:8px">VisionAI 실시간 화면 · 초록 뼈대 = 카메라가 본 사람 · 주황 원 = 레이더 표적 · 숫자 = 지게차까지 거리</p>
<img src="/stream" alt="VisionAI 카메라 화면" style="max-width:100%;height:auto"></body>"""


class WebView:
    def __init__(self, port=8090, host="0.0.0.0", quality=70, max_fps=8.0):
        self.port, self.host, self.quality = port, host, quality
        self.min_gap = 1.0 / max_fps if max_fps > 0 else 0.0
        self.jpg, self.seq, self.clients = None, 0, 0
        self.cond = threading.Condition()
        self._last = 0.0
        self.server = None

    @property
    def wanted(self):
        """지금 보는 사람이 있고 보낼 때가 됐는지 (아니면 프레임을 그리거나 인코딩할 필요 없음)."""
        return self.clients > 0 and time.monotonic() - self._last >= self.min_gap

    def update(self, frame):
        if not self.wanted:
            return
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
        if not ok:
            return
        self._last = time.monotonic()
        with self.cond:
            self.jpg, self.seq = buf.tobytes(), self.seq + 1
            self.cond.notify_all()

    def _next(self, seq, timeout=5.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != seq, timeout)
            return self.jpg, self.seq

    def start(self):
        view = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    body = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                elif self.path == "/snapshot.jpg":
                    view.clients += 1          # 한 장을 만들게 한다
                    try:
                        jpg, _ = view._next(view.seq if view.jpg is None else -1, timeout=5)
                    finally:
                        view.clients -= 1
                    if not jpg:
                        self.send_error(503, "no frame yet")
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpg)))
                    self.end_headers()
                    self.wfile.write(jpg)
                elif self.path == "/stream":
                    self.send_response(200)
                    self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    view.clients += 1
                    seq = -1
                    try:
                        while True:
                            jpg, seq = view._next(seq)
                            if not jpg:
                                continue
                            self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                             + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        pass
                    finally:
                        view.clients -= 1
                else:
                    self.send_error(404)

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
