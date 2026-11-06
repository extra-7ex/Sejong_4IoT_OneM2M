#!/usr/bin/env python3
"""4iot vision benchmark: YOLO pose FPS on Raspberry Pi 4.

Examples
  python bench_pose.py --model yolo11n-pose_ncnn_320 --imgsz 320 --source walk.mp4 --label C
  python bench_pose.py --model yolo11n-pose_ncnn_320 --imgsz 320 --source picam --label C-cam
"""
import argparse
import csv
import os
import statistics
import subprocess
import time
from datetime import datetime

import cv2
from ultralytics import YOLO


def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read()) / 1000.0
    except OSError:
        return float("nan")


def throttled():
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2)
        return out.stdout.strip().split("=")[-1]
    except Exception:
        return "n/a"


class Source:
    """picam = Pi camera (Picamera2), a number = USB camera, anything else = video file (looped)."""

    def __init__(self, spec, width=640, height=480):
        self.kind = "picam" if spec == "picam" else ("usb" if spec.isdigit() else "file")
        if self.kind == "picam":
            from picamera2 import Picamera2
            self.cam = Picamera2()
            cfg = self.cam.create_video_configuration(main={"size": (width, height), "format": "RGB888"})
            self.cam.configure(cfg)
            self.cam.start()
            time.sleep(1.0)
        else:
            self.cap = cv2.VideoCapture(int(spec) if self.kind == "usb" else spec)
            if self.kind == "usb":
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            if not self.cap.isOpened():
                raise SystemExit(f"cannot open source: {spec}")

    def read(self):
        if self.kind == "picam":
            return self.cam.capture_array()  # "RGB888" here is BGR byte order, as OpenCV/YOLO expect
        ok, frame = self.cap.read()
        if not ok and self.kind == "file":
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if not ok:
            raise SystemExit("frame read failed")
        return frame

    def close(self):
        if self.kind == "picam":
            self.cam.stop()
        else:
            self.cap.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="yolo11n-pose.pt or an NCNN folder")
    ap.add_argument("--imgsz", type=int, default=320)
    ap.add_argument("--source", default="picam", help="picam | 0 (USB) | video.mp4")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--warmup", type=int, default=10)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default="results.csv")
    a = ap.parse_args()

    model = YOLO(a.model, task="pose")
    src = Source(a.source)

    for _ in range(a.warmup):
        model.predict(src.read(), imgsz=a.imgsz, verbose=False)

    lat, grab, people, temps = [], [], [], [cpu_temp()]
    saved = False
    t_end = time.time() + a.seconds
    t_start = time.time()
    last_temp = t_start
    while time.time() < t_end:
        t0 = time.perf_counter()
        frame = src.read()
        t1 = time.perf_counter()
        r = model.predict(frame, imgsz=a.imgsz, verbose=False)[0]
        t2 = time.perf_counter()
        grab.append((t1 - t0) * 1000)
        lat.append((t2 - t1) * 1000)
        people.append(len(r.boxes))
        if not saved and len(r.boxes) > 0:
            cv2.imwrite(f"sample_{a.label or 'run'}.jpg", r.plot())
            saved = True
        if time.time() - last_temp > 5:
            temps.append(cpu_temp())
            last_temp = time.time()
    elapsed = time.time() - t_start
    src.close()

    n = len(lat)
    row = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "label": a.label,
        "model": os.path.basename(a.model.rstrip("/")),
        "imgsz": a.imgsz,
        "source": a.source,
        "frames": n,
        "fps": round(n / elapsed, 2),
        "infer_ms_mean": round(statistics.mean(lat), 1),
        "infer_ms_p95": round(sorted(lat)[max(int(n * 0.95) - 1, 0)], 1),
        "grab_ms_mean": round(statistics.mean(grab), 1),
        "people_mean": round(statistics.mean(people), 2),
        "temp_max_c": round(max(temps), 1),
        "throttled": throttled(),
        "load_1min": round(os.getloadavg()[0], 2),
    }
    new = not os.path.exists(a.out)
    with open(a.out, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)
    print("\n".join(f"{k:>14}: {v}" for k, v in row.items()))


if __name__ == "__main__":
    main()
