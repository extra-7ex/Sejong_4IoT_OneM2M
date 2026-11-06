#!/usr/bin/env python3
"""카메라 설치용 실시간 화면 (Pi에서). 브라우저로 http://4Iot.local:8080 을 열면 카메라 화면이 보인다.

화면에 안내선을 그린다: 바닥과 벽이 만나는 선이 'horizon target' 근처(화면 위 1/4)에 오면 각도가 적당하다.
/snapshot.jpg 는 지금 화면 한 장 (Claude가 확인용으로 받아 본다).
카메라는 한 프로그램만 열 수 있으니 VisionAI(main.py)를 돌릴 때는 끈다.

  python tools/live_view.py [--source 0] [--port 8080]
"""
import argparse
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

PAGE = b"""<!doctype html><meta charset="utf-8"><title>camera</title>
<body style="margin:0;background:#111;color:#ddd;font-family:sans-serif;text-align:center">
<p>C270 &middot; 640x480 &middot; <b>green line</b> = floor/wall line target (top 1/4)</p>
<img src="/stream" style="max-width:100%;height:auto"></body>"""


class Cam:
    def __init__(self, src, size=(640, 480)):
        self.cap = cv2.VideoCapture(src)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, size[1])
        self.jpg, self.lock = None, threading.Lock()
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while True:
            ok, f = self.cap.read()
            if not ok:
                time.sleep(0.1)
                continue
            h, w = f.shape[:2]
            cv2.line(f, (0, h // 4), (w, h // 4), (0, 220, 0), 2)
            cv2.putText(f, "horizon target", (8, h // 4 - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 0), 1)
            cv2.line(f, (w // 2, 0), (w // 2, h), (200, 200, 200), 1)
            for y in (h // 2, 3 * h // 4):
                cv2.line(f, (0, y), (w, y), (120, 120, 120), 1)
            cv2.putText(f, time.strftime("%H:%M:%S"), (w - 90, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self.lock:
                    self.jpg = buf.tobytes()

    def get(self):
        with self.lock:
            return self.jpg


def handler(cam):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(PAGE)
            elif self.path == "/snapshot.jpg":
                jpg = cam.get()
                self.send_response(200 if jpg else 503)
                self.send_header("Content-Type", "image/jpeg")
                self.end_headers()
                if jpg:
                    self.wfile.write(jpg)
            elif self.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=f")
                self.end_headers()
                try:
                    while True:
                        jpg = cam.get()
                        if jpg:
                            self.wfile.write(b"--f\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                        time.sleep(0.1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=int, default=0)
    ap.add_argument("--port", type=int, default=8080)
    a = ap.parse_args()
    cam = Cam(a.source)
    print(f"live view: http://<Pi>:{a.port}  (Ctrl+C to stop)", flush=True)
    ThreadingHTTPServer(("0.0.0.0", a.port), handler(cam)).serve_forever()


if __name__ == "__main__":
    main()
