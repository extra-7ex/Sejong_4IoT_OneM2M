"""YOLO11n-pose 사람 검출 + 관절 + ByteTrack 추적 id (CLAUDE.md 3장)."""
import time
from dataclasses import dataclass

import cv2
import numpy as np
from ultralytics import YOLO

# COCO 17 키포인트 연결선
SKELETON = [
    (5, 6), (5, 7), (7, 9), (6, 8), (8, 10),          # 어깨·팔
    (5, 11), (6, 12), (11, 12),                       # 몸통
    (11, 13), (13, 15), (12, 14), (14, 16),           # 다리
    (0, 1), (0, 2), (1, 3), (2, 4),                   # 얼굴
]


@dataclass
class Person:
    id: int | None           # 추적 id (추적이 아직 안 붙었으면 None)
    box: np.ndarray          # xyxy, px
    conf: float
    kpts: np.ndarray         # (17, 3): x, y, conf


class PoseDetector:
    def __init__(self, path, imgsz=640, conf=0.4, tracker="bytetrack.yaml"):
        self.model = YOLO(path, task="pose")
        self.imgsz = imgsz
        self.conf = conf
        self.tracker = tracker
        self.infer_ms = 0.0

    def detect(self, frame):
        t0 = time.perf_counter()
        r = self.model.track(frame, imgsz=self.imgsz, conf=self.conf, classes=[0],
                             tracker=self.tracker, persist=True, verbose=False)[0]
        self.infer_ms = (time.perf_counter() - t0) * 1000

        if r.boxes is None or len(r.boxes) == 0:
            return []
        boxes = r.boxes.xyxy.cpu().numpy()
        confs = r.boxes.conf.cpu().numpy()
        ids = r.boxes.id.int().cpu().tolist() if r.boxes.id is not None else [None] * len(boxes)
        kpts = r.keypoints.data.cpu().numpy() if r.keypoints is not None else np.zeros((len(boxes), 17, 3))
        return [Person(i, b, float(c), k) for i, b, c, k in zip(ids, boxes, confs, kpts)]


def _color(track_id):
    if track_id is None:
        return (200, 200, 200)
    rng = np.random.default_rng(track_id)
    return tuple(int(c) for c in rng.integers(64, 256, 3))


def draw_people(frame, people, kp_min_conf=0.3, notes=None):
    """notes: 사람마다 [(글자, BGR색), ...] — 박스 안 왼쪽 위에 한 줄씩."""
    for n, p in enumerate(people):
        color = _color(p.id)
        x1, y1, x2, y2 = p.box.astype(int)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"id {p.id if p.id is not None else '-'}  {p.conf:.2f}"
        cv2.putText(frame, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        for i, (text, c) in enumerate(notes[n] if notes else []):
            org = (x1 + 4, max(y1, 0) + 20 + i * 20)
            cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 4)
            cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1)

        ok = p.kpts[:, 2] >= kp_min_conf
        pts = p.kpts[:, :2].astype(int)
        for a, b in SKELETON:
            if ok[a] and ok[b]:
                cv2.line(frame, tuple(pts[a]), tuple(pts[b]), color, 2)
        for i in np.flatnonzero(ok):
            cv2.circle(frame, tuple(pts[i]), 3, (0, 0, 255), -1)
    return frame
