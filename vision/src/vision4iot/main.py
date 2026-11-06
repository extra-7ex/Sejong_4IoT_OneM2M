"""VisionAI 실행 진입점: 영상 → 사람·관절·자세 → 바닥 좌표 → 레이더와 융합 → fusedTracks (CLAUDE.md 3장).

  python -m vision4iot.main                      # config.yaml
  python -m vision4iot.main --headless           # 화면 없이 1초마다 FPS·융합 결과 출력
  python -m vision4iot.main --source data/walk.mp4
  python -m vision4iot.main --config config.pi.yaml --radar onem2m --output onem2m --base-url http://127.0.0.1:3000
"""
import argparse
import sys
import time

import cv2
import numpy as np

from vision4iot import calib
from vision4iot.config import load_config, resolve
from vision4iot.detector import PoseDetector, draw_people
from vision4iot.fusion import CamPerson, FusionParams, fuse, message
from vision4iot.posture import PostureParams, PostureVoter, classify
from vision4iot.publisher import make_publisher
from vision4iot.radar.base import Target
from vision4iot.radar.onem2m_in import OneM2MRadar
from vision4iot.radar.sim import RadarSim
from vision4iot.source import Source, SourceError

POSTURE_COLOR = {"standing": (0, 200, 0), "crouching": (0, 165, 255), "lying": (0, 0, 255), None: (180, 180, 180)}
FOOT_COLOR = {"feet": (0, 255, 255), "box": (255, 255, 0), "box_cut": (255, 0, 255)}


def draw_hud(frame, fps, infer_ms, n_people):
    lines = [f"FPS {fps:5.1f}", f"infer {infer_ms:5.1f} ms", f"people {n_people}"]
    cv2.rectangle(frame, (0, 0), (170, 8 + 22 * len(lines)), (0, 0, 0), -1)
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (8, 22 + i * 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)


def floor_text(f, foot_src):
    """박스가 화면 아래에서 잘려 발이 안 보이면 실제보다 멀게 나오므로 '>='로 표시."""
    x, y, d = f
    return f"x {x:+.2f} y {y:.2f} d {'>=' if foot_src == 'box_cut' else ''}{d:.2f}m"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--source", help="config의 source 대신 (webcam:N | 파일 | picam)")
    ap.add_argument("--headless", action="store_true", help="화면 없이 1초마다 FPS 출력")
    ap.add_argument("--debug", action="store_true", help="자세 판정 값(몸통 각도·비율·무릎 각도) 표시")
    ap.add_argument("--calib", help="config의 calib.file 대신")
    ap.add_argument("--radar", choices=["sim", "onem2m", "none"], help="config의 radar.source 대신 (sim = 카메라 위치로 가짜 레이더)")
    ap.add_argument("--output", choices=["stdout", "jsonl", "onem2m", "none"], help="config의 output.mode 대신")
    ap.add_argument("--base-url", help="CSE 주소, 예 http://127.0.0.1:3000 (config onem2m.base_url 대신)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    headless = args.headless or cfg.get("headless", False)
    debug = args.debug or cfg["posture"].get("show_debug", False)
    spec = args.source or cfg["source"]
    if not (spec == "picam" or spec.startswith("webcam:")):
        spec = resolve(spec)

    try:
        src = Source(spec, cfg.get("frame_size", (640, 480)))
    except SourceError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    m = cfg["model"]
    det = PoseDetector(resolve(m["path"]), imgsz=m["imgsz"], conf=m["conf"], tracker=m["tracker"])
    pp = PostureParams.from_cfg(cfg["posture"])
    voter = PostureVoter(pp.vote_frames)

    calib_path = resolve(args.calib or cfg["calib"]["file"])
    cal = calib.load(calib_path)
    if cal is None:
        print(f"WARN: no calibration at {calib_path} - floor x, y, dist disabled. "
              "Run: python tools/calibrate.py", file=sys.stderr)
    size_checked = False

    # 레이더 입력 (CLAUDE.md 9장): onem2m = tinyIoT radar/la, sim = 카메라 사람 위치 + 잡음(장비 없을 때 융합 시험)
    rsrc = args.radar or cfg["radar"]["source"]
    radar_in, sim = None, None
    if rsrc == "onem2m":
        radar_in = OneM2MRadar.from_cfg(cfg, args.base_url).start()
    elif rsrc == "sim":
        sim = RadarSim.from_cfg({**cfg["radar"]["sim"], "mode": "from_camera"}, resolve)
        print("NOTE: radar = sim (camera positions + noise) - not a real radar", file=sys.stderr)
    fparams = FusionParams.from_cfg(cfg.get("fusion", {}), cfg["thresholds"])
    out_mode = args.output or cfg["output"]["mode"]
    pub = None if out_mode == "none" else make_publisher(cfg, out_mode, args.base_url)
    in_view = cal.in_view if cal is not None else (lambda x, y: False)   # 보정 없으면 유령 판정 안 함
    frame_no, last_tracks, radar_ok = 0, [], None

    fps, frames, t_win = 0.0, 0, time.perf_counter()
    misses = 0
    try:
        while True:
            frame = src.read()
            ts = time.time()
            if frame is None:
                misses += 1
                if misses == 1 or misses % 30 == 0:
                    print(f"WARN: frame read failed ({misses})", file=sys.stderr)
                if pub is not None and misses % 10 == 1:      # 카메라가 끊긴 것을 숨기지 않는다 (4장)
                    pub.publish(message(ts, frame_no, False, [], now=time.time()))
                time.sleep(0.05)
                continue
            misses = 0
            frame_no += 1

            people = det.detect(frame)
            fsize = (frame.shape[1], frame.shape[0])
            raw = [classify(p.kpts, p.box, pp, fsize) for p in people]
            postures = [voter.update(p.id, r.label) for p, r in zip(people, raw)]
            voter.next_frame()

            if cal is not None and not size_checked:
                if msg := cal.check_frame_size(fsize):
                    print(f"WARN: {msg}", file=sys.stderr)
                size_checked = True
            feet = [calib.foot_point(p.kpts, p.box, pp.kp_min_conf, fsize, pp.edge_margin_px) for p in people]
            floor = [None] * len(people)                 # (x, y, dist_m) 또는 None
            if cal is not None and people:
                xy = cal.to_floor([fp for fp, _ in feet], fsize)
                floor = [None if np.isnan(v).any() else (v[0], v[1], calib.dist_m(*v)) for v in xy]

            # 융합 (7장) → fusedTracks (10장)
            cams = [CamPerson(p.id, f[0], f[1], s, p.conf, fsrc == "box_cut")
                    for p, s, f, (_, fsrc) in zip(people, postures, floor, feet) if f is not None]
            if radar_in is not None:
                radar, radar_ok = radar_in.get()
            elif sim is not None:
                radar = sim.get_targets(ts, [Target(c.id if c.id is not None else -1, c.x, c.y, 0.0) for c in cams])
                radar_ok = True
            else:
                radar, radar_ok = [], None
            last_tracks = fuse(radar, cams, fparams, cam_ok=True, in_view=in_view) if cal is not None else []
            if pub is not None:
                pub.publish(message(ts, frame_no, True, last_tracks, radar_ok, now=time.time()))

            frames += 1
            now = time.perf_counter()
            if now - t_win >= 1.0:
                fps = frames / (now - t_win)
                frames, t_win = 0, now
                if headless:
                    who = " ".join(f"{p.id}:{s}" + (f"@{floor_text(f, src)}" if f else "")
                                   for p, s, f, (_, src) in zip(people, postures, floor, feet))
                    print(f"FPS {fps:5.1f} | infer {det.infer_ms:5.1f} ms | people {len(people)} {who}", flush=True)
                    fused = " ".join(f"{t['id']}:{t['state']} {t['dist_m']:.2f}m {t['advice']}" for t in last_tracks)
                    extra = ""
                    if radar_in is not None and radar_in.last_error:
                        extra += f" | radar error: {radar_in.last_error}"
                    if pub is not None and getattr(pub, "last_error", None):
                        extra += f" | output error: {pub.last_error}"
                    print(f"    radar {rsrc} ok={radar_ok} | fused [{fused}]{extra}", flush=True)
                    if debug:
                        for p, r in zip(people, raw):
                            print(f"    id {p.id} raw={r.label} {r.debug_text()}", flush=True)

            if not headless:
                notes = []
                by_id = {t["id"]: t for t in last_tracks}
                for p, s, r, f, (_, src_) in zip(people, postures, raw, floor, feet):
                    n = [(s or "?", POSTURE_COLOR[s])]
                    if f:
                        n.append((floor_text(f, src_), FOOT_COLOR[src_] if src_ == "box_cut" else (255, 255, 255)))
                    if (t := by_id.get(p.id)) is not None:
                        n.append((f"{t['state']} {t['advice']}", (0, 0, 255) if t["advice"] == "raise" else (255, 255, 255)))
                    if debug:
                        n += [(f"raw {r.label or '?'}", POSTURE_COLOR[r.label]),
                              (r.debug_text(), (255, 255, 255))]
                    notes.append(n)
                draw_people(frame, people, pp.kp_min_conf, notes)
                for fp, src_ in feet:
                    cv2.circle(frame, tuple(np.round(fp).astype(int)), 6, FOOT_COLOR[src_], 2)
                draw_hud(frame, fps, det.infer_ms, len(people))
                cv2.imshow("vision4iot", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        src.close()
        if radar_in is not None:
            radar_in.stop()
        if pub is not None:
            pub.close()
            if hasattr(pub, "sent"):
                print(f"fusedTracks sent {pub.sent}, failed {pub.failed}", file=sys.stderr)
        if not headless:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
