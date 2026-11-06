#!/usr/bin/env python3
"""웹캠이 열리고 프레임이 읽히는지만 확인한다 (화면 없이 동작).

  python tools/check_webcam.py            # 0번 카메라
  python tools/check_webcam.py --index 1
"""
import argparse
import sys
import time

import cv2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--frames", type=int, default=30)
    args = ap.parse_args()

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(args.index, backend)
    if not cap.isOpened():
        print(f"FAIL: camera {args.index} did not open")
        return 1

    ok = 0
    t0 = time.perf_counter()
    for _ in range(args.frames):
        ret, frame = cap.read()
        ok += bool(ret and frame is not None)
    dt = time.perf_counter() - t0
    cap.release()

    if ok == 0:
        print(f"FAIL: camera {args.index} opened but returned no frames")
        return 1
    h, w = frame.shape[:2]
    print(f"OK: camera {args.index} {w}x{h}, {ok}/{args.frames} frames, {ok / dt:.1f} fps")
    return 0


if __name__ == "__main__":
    sys.exit(main())
