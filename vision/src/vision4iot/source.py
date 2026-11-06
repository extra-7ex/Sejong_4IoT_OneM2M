"""영상 입력: config `source` 하나로 webcam:N / 동영상 파일 / picam (CLAUDE.md 12장).

read()는 실패해도 예외를 던지지 않고 None을 돌려준다 → 호출 쪽이 cam_ok=false를 정직하게 보낸다(4장).
"""
import sys
import time

import cv2


class SourceError(RuntimeError):
    pass


class Source:
    def __init__(self, spec, size=(640, 480), loop_file=True):
        self.spec = str(spec)
        self.size = tuple(size)
        self.loop_file = loop_file
        self.cam = None
        self.cap = None
        if self.spec == "picam":
            self.kind = "picam"
            self._open_picam()
        elif self.spec.startswith("webcam:"):
            self.kind = "webcam"
            self._open_webcam(int(self.spec.split(":", 1)[1]))
        else:
            self.kind = "file"
            self.cap = cv2.VideoCapture(self.spec)
            if not self.cap.isOpened():
                raise SourceError(f"cannot open video file: {self.spec}")

    def _open_webcam(self, index):
        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)
        if not self.cap.isOpened():
            raise SourceError(f"cannot open webcam {index}")
        w, h = self.size
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    def _open_picam(self):
        try:
            from picamera2 import Picamera2  # Pi에서만 있음 (apt, venv --system-site-packages)
        except ImportError as e:
            raise SourceError("picam needs picamera2 (Raspberry Pi only); use webcam:N or a video file here") from e
        w, h = self.size
        self.cam = Picamera2()
        self.cam.configure(self.cam.create_video_configuration(main={"size": (w, h), "format": "RGB888"}))
        self.cam.start()
        time.sleep(1.0)

    def read(self):
        """BGR 프레임 또는 None(실패)."""
        if self.kind == "picam":
            try:
                return self.cam.capture_array()  # "RGB888"은 메모리상 BGR 순서 = OpenCV/YOLO가 기대하는 순서
            except Exception:
                return None
        ok, frame = self.cap.read()
        if not ok and self.kind == "file" and self.loop_file:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        return frame if ok else None

    def close(self):
        if self.cam is not None:
            self.cam.stop()
        if self.cap is not None:
            self.cap.release()
