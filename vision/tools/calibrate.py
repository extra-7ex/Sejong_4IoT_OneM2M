#!/usr/bin/env python3
"""바닥 호모그래피 보정 → calib/H.json (+ 확인용 calib/H_check.jpg). CLAUDE.md 8장.

바닥에 테이프 등으로 4점 이상(6점 이상 권장, 한 줄로 늘어서지 않게) 표시하고 실제 좌표(m)를 잰다.
좌표: 원점 = 지게차 후면 중앙(레이더) 바닥, x 오른쪽 +, y 지게차에서 멀어지는 쪽 + (5장).

노트북(화면 있음)
  python tools/calibrate.py                       # config의 source 실시간 → 스페이스로 멈춤 → 클릭
  python tools/calibrate.py --image calib/pi.jpg  # 저장한 사진으로 클릭

Pi(화면 없음)
  python tools/calibrate.py --grab calib/pi.jpg   # 사진 한 장 저장 → 노트북으로 옮겨 --image로 클릭 → H.json을 Pi로
  python tools/calibrate.py --image calib/pi.jpg --points calib/points.csv   # 클릭 없이 점 파일로

points.csv: 한 줄에 u,v,x,y (u,v = 사진 px, x,y = 실제 m). '#'로 시작하면 주석.

클릭 화면 키: 클릭 → 터미널에 "x y" 입력 / u 되돌리기 / s 또는 Enter 저장(4점 이상) / q·Esc 저장 없이 종료
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

from vision4iot import calib
from vision4iot.config import load_config, resolve
from vision4iot.source import Source, SourceError

WIN = "calibrate"


def read_image(path):
    """cv2.imread는 Windows에서 한글 등 비ASCII 경로를 못 읽는다 → 바이트로 읽어 디코드."""
    try:
        return cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    except OSError:
        return None


def write_image(path, img):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    cv2.imencode(Path(path).suffix or ".jpg", img)[1].tofile(str(path))


def grab_frame(cfg, spec, live):
    """config source에서 한 장. live=True면 화면에 띄우고 스페이스로 멈춘 장면."""
    src = Source(spec, cfg.get("frame_size", (640, 480)))
    try:
        frame = None
        for _ in range(10):                      # 자동 노출이 자리 잡게 몇 장 버림
            frame = src.read()
        if not live:
            return frame
        print("live view: SPACE = freeze this frame, q = quit")
        while True:
            f = src.read()
            if f is None:
                continue
            frame = f
            view = f.copy()
            cv2.putText(view, "SPACE: freeze   q: quit", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.imshow(WIN, view)
            k = cv2.waitKey(1) & 0xFF
            if k == ord(" "):
                return frame
            if k in (ord("q"), 27):
                return None
    finally:
        src.close()


def read_points_csv(path):
    img, world = [], []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        vals = [float(v) for v in line.replace(",", " ").split()]
        if len(vals) != 4:
            raise ValueError(f"expected u,v,x,y: {line!r}")
        img.append(vals[:2])
        world.append(vals[2:])
    return img, world


def ask_world(n):
    while True:
        s = input(f"  point {n} real floor position 'x y' in m (empty = cancel this click): ").strip()
        if not s:
            return None
        try:
            x, y = (float(v) for v in s.replace(",", " ").split())
            return x, y
        except ValueError:
            print("    two numbers please, e.g. 0.5 2.0")


def draw_points(img, img_pts, world_pts):
    for i, ((u, v), (x, y)) in enumerate(zip(img_pts, world_pts), 1):
        c = (int(u), int(v))
        cv2.circle(img, c, 5, (0, 0, 255), -1)
        cv2.putText(img, f"{i} ({x:g},{y:g})", (c[0] + 7, c[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(img, f"{i} ({x:g},{y:g})", (c[0] + 7, c[1] - 7), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)


def click_points(frame):
    img_pts, world_pts = [], []
    clicked = []
    cv2.namedWindow(WIN)
    cv2.setMouseCallback(WIN, lambda ev, x, y, *_: clicked.append((x, y)) if ev == cv2.EVENT_LBUTTONDOWN else None)
    print("click floor marks; after each click type its real 'x y' (m) in this terminal. "
          "u = undo, s/Enter = save, q = quit")
    while True:
        view = frame.copy()
        draw_points(view, img_pts, world_pts)
        msg = f"{len(img_pts)} pts  click=add  u=undo  s=save(>=4)  q=quit"
        cv2.putText(view, msg, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
        cv2.imshow(WIN, view)
        k = cv2.waitKey(20) & 0xFF
        if clicked:
            u, v = clicked.pop(0)
            clicked.clear()
            print(f"clicked px ({u}, {v})")
            xy = ask_world(len(img_pts) + 1)
            if xy is not None:
                img_pts.append((u, v))
                world_pts.append(xy)
        elif k == ord("u") and img_pts:
            img_pts.pop()
            world_pts.pop()
        elif k in (ord("s"), 13):
            if len(img_pts) >= 4:
                return img_pts, world_pts
            print("need at least 4 points")
        elif k in (ord("q"), 27):
            return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--source", help="config의 source 대신")
    ap.add_argument("--image", help="카메라 대신 저장한 사진으로 보정")
    ap.add_argument("--points", help="클릭 대신 u,v,x,y 점 파일 (화면 없이)")
    ap.add_argument("--grab", metavar="OUT.jpg", help="사진 한 장만 저장하고 끝 (Pi, 화면 없이)")
    ap.add_argument("--out", help="기본: config calib.file")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    spec = args.source or cfg["source"]
    if not (spec == "picam" or spec.startswith("webcam:")):
        spec = resolve(spec)
    out = Path(resolve(args.out or cfg["calib"]["file"]))

    try:
        if args.grab:
            frame = grab_frame(cfg, spec, live=False)
            if frame is None:
                print("ERROR: no frame from source", file=sys.stderr)
                return 1
            Path(args.grab).parent.mkdir(parents=True, exist_ok=True)
            write_image(args.grab, frame)
            print(f"saved {args.grab} ({frame.shape[1]}x{frame.shape[0]})")
            return 0

        if args.image:
            frame = read_image(args.image)
            if frame is None:
                print(f"ERROR: cannot read image {args.image}", file=sys.stderr)
                return 1
        else:
            frame = grab_frame(cfg, spec, live=not args.points)
            if frame is None:
                print("quit (no frame)")
                return 1
    except SourceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    if args.points:
        img_pts, world_pts = read_points_csv(args.points)
    else:
        img_pts, world_pts = click_points(frame)
        cv2.destroyAllWindows()
        if img_pts is None:
            print("quit without saving")
            return 1

    try:
        H, err = calib.fit_homography(img_pts, world_pts)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    size = (frame.shape[1], frame.shape[0])
    note = args.image or spec
    calib.save(out, H, img_pts, world_pts, err, size, note=f"source: {note}")

    check = frame.copy()
    c = calib.Calib(H, size)
    calib.draw_floor_grid(check, c)
    draw_points(check, img_pts, world_pts)
    check_path = out.with_name(out.stem + "_check.jpg")
    write_image(check_path, check)

    print(f"saved {out}  ({len(img_pts)} points, image {size[0]}x{size[1]})")
    print(f"reprojection error: mean {err['mean'] * 100:.1f} cm, max {err['max'] * 100:.1f} cm  "
          f"per point (cm): {[round(e * 100, 1) for e in err['per_point']]}")
    print(f"check image: {check_path}  (floor grid every 0.5 m; it should sit flat on the floor)")
    for w in calib.sanity_warnings(H, world_pts, size, cfg["fusion"].get("camera_fov_deg")):
        print(f"WARN: {w}")
    if len(img_pts) == 4:
        print("NOTE: with exactly 4 points the error is always ~0 - use 6+ points to see real accuracy")
    elif err["mean"] > 0.10:
        print("WARN: mean error > 10 cm - check the measured positions or clicks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
