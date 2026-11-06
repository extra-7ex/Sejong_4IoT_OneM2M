"""호모그래피 보정: 화면 px → 바닥 좌표 m (CLAUDE.md 5·8장).

calib/H.json = {H, date, reproj_err_m, image_size, points}. image_size가 실행 중 프레임 크기와 다르면
같은 화면비일 때만 크기 비율로 맞춰 쓴다(다른 해상도로 찍은 사진으로 보정해도 됨).
"""
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

L_ANKLE, R_ANKLE = 15, 16


def fit_homography(img_pts, world_pts):
    """4점 이상 → (H, 재투영 오차 dict). 오차는 보정점을 H로 옮겼을 때 실제 좌표와의 거리(m)."""
    img = np.asarray(img_pts, dtype=np.float64).reshape(-1, 2)
    world = np.asarray(world_pts, dtype=np.float64).reshape(-1, 2)
    if len(img) < 4 or len(img) != len(world):
        raise ValueError("need at least 4 matching image/world points")
    H, _ = cv2.findHomography(img, world, 0)      # 0 = 모든 점 최소제곱 (RANSAC 아님)
    if H is None:
        raise ValueError("homography failed — points may be collinear")
    err = np.linalg.norm(project(H, img) - world, axis=1)
    return H, {"mean": float(err.mean()), "max": float(err.max()), "per_point": [round(float(e), 4) for e in err]}


def project(H, pts):
    """(N, 2) px → (N, 2) m. 지평선 위쪽처럼 투영이 안 되는 점은 NaN."""
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    hom = np.hstack([pts, np.ones((len(pts), 1))]) @ H.T
    w = hom[:, 2:3]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = hom[:, :2] / w
    out[np.abs(w[:, 0]) < 1e-12] = np.nan
    return out


@dataclass
class Calib:
    H: np.ndarray
    image_size: tuple          # 보정할 때 사진 크기 (w, h)
    date: str = ""
    reproj_err_m: float | None = None

    def to_floor(self, pts, frame_size=None):
        """화면점(N, 2) px → 바닥 (N, 2) m. frame_size(w, h)가 보정 사진과 다르면 비율로 맞춘다."""
        pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
        if frame_size is not None and tuple(frame_size) != tuple(self.image_size):
            pts = pts * (np.array(self.image_size, dtype=np.float64) / np.array(frame_size, dtype=np.float64))
        return project(self.H, pts)

    def in_view(self, x, y, margin_px=0):
        """바닥점 (x, y) m가 보정 사진 화면 안에 찍히는지. 카메라 뒤(지평선 너머)로 넘어간 점은 False.
        유령 판정(7장 "카메라 화각 안")에 쓴다 — 화면 아래보다 가까운 바닥도 False라 그런 표적은 유령으로 몰지 않는다."""
        Hinv = np.linalg.inv(self.H)
        w, h = self.image_size
        ref = Hinv @ np.append(project(self.H, [[w / 2, h - 1]])[0], 1.0)
        p = Hinv @ np.array([x, y, 1.0])
        if p[2] * np.sign(ref[2]) <= 1e-12:
            return False
        u, v = p[0] / p[2], p[1] / p[2]
        return margin_px <= u < w - margin_px and margin_px <= v < h - margin_px

    def check_frame_size(self, frame_size):
        """맞지 않으면 경고 문장, 괜찮으면 None."""
        cw, ch = self.image_size
        fw, fh = frame_size
        if (cw, ch) == (fw, fh):
            return None
        if abs(cw / ch - fw / fh) > 0.01:
            return (f"calib image {cw}x{ch} and frame {fw}x{fh} have different aspect ratios - "
                    "floor coordinates will be wrong; recalibrate at this resolution")
        return f"calib image {cw}x{ch} scaled to frame {fw}x{fh}"


def save(path, H, img_pts, world_pts, err, image_size, note=""):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "H": np.asarray(H).tolist(),
        "date": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reproj_err_m": {"mean": round(err["mean"], 4), "max": round(err["max"], 4)},
        "image_size": list(image_size),
        "points": [{"px": [round(float(u), 1), round(float(v), 1)], "m": [float(x), float(y)], "err_m": e}
                   for (u, v), (x, y), e in zip(np.asarray(img_pts), np.asarray(world_pts), err["per_point"])],
        "note": note,
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def load(path):
    """없으면 None (호출 쪽이 경고하고 계속 동작)."""
    path = Path(path)
    if not path.exists():
        return None
    d = json.loads(path.read_text(encoding="utf-8"))
    return Calib(np.array(d["H"], dtype=np.float64), tuple(d["image_size"]), d.get("date", ""),
                 (d.get("reproj_err_m") or {}).get("mean"))


def foot_point(kpts, box, kp_min_conf=0.3, frame_size=None, edge_margin_px=5):
    """사람 바닥점(px)과 출처.

    출처: "feet" = 좌우는 두 발목 중점, 앞뒤는 박스 맨 아래(발바닥·발끝) / "box" = 박스 아래 중앙(발목 안 보임)
          / "box_cut" = 박스가 화면 아래 끝에 닿음(발이 화면 밖).
    발목은 바닥에서 8~10cm 떠 있어 비스듬한 카메라에선 실제보다 **멀게** 나온다(2026-11-06 C270 실측: 1.5m 점이 1.81m).
    박스 맨 아래는 발끝이라 조금 **가깝게** 나온다(같은 실측 1.37m) → 안전한 쪽으로 틀리므로 앞뒤는 박스 아래를 쓴다.
    box_cut이면 실제보다 멀게 계산된다 → 위험 쪽으로 틀리므로 표시해 둔다(보이면 발목 중점을 쓴다).
    """
    k = np.asarray(kpts, dtype=np.float64)
    ankles = k[L_ANKLE, 2] >= kp_min_conf and k[R_ANKLE, 2] >= kp_min_conf
    mid = (k[L_ANKLE, :2] + k[R_ANKLE, :2]) / 2
    x1, y1, x2, y2 = box
    if frame_size is not None and y2 >= frame_size[1] - edge_margin_px:
        return (mid if ankles else np.array([(x1 + x2) / 2, y2], dtype=np.float64)), "box_cut"
    if ankles:
        return np.array([mid[0], y2], dtype=np.float64), "feet"
    return np.array([(x1 + x2) / 2, y2], dtype=np.float64), "box"


def draw_floor_grid(img, calib, x_range=(-2.0, 2.0), y_range=(0.5, 6.0), step=0.5):
    """확인용: 바닥 격자(m)를 사진 위에 그린다(보정 사진 크기 기준). 1m 선은 굵게, 원점 쪽 축은 노랑."""
    Hinv = np.linalg.inv(calib.H)
    w, h = calib.image_size
    # 카메라 앞쪽 바닥점의 w 부호 — 카메라 뒤(지평선 너머)로 넘어간 점은 버린다
    ref = np.append(project(calib.H, [[w / 2, h - 1]])[0], 1.0) @ Hinv.T
    sign = np.sign(ref[2])
    xs = np.arange(x_range[0], x_range[1] + 1e-9, step)
    ys = np.arange(y_range[0], y_range[1] + 1e-9, step)
    lines = [((x, y_range[0]), (x, y_range[1]), x) for x in xs] + [((x_range[0], y), (x_range[1], y), y) for y in ys]
    for a, b, v in lines:
        seg = np.linspace(a, b, 40)
        hom = np.hstack([seg, np.ones((len(seg), 1))]) @ Hinv.T
        ok = hom[:, 2] * sign > 1e-9
        px = np.full((len(seg), 2), np.nan)
        px[ok] = hom[ok, :2] / hom[ok, 2:3]
        major = abs(v - round(v)) < 1e-6
        color = (0, 255, 255) if abs(v) < 1e-6 else (255, 255, 0) if major else (200, 200, 120)
        for p, q in zip(px[:-1], px[1:]):
            if np.isfinite(p).all() and np.isfinite(q).all() and max(abs(p).max(), abs(q).max()) < 4 * max(w, h):
                cv2.line(img, tuple(np.round(p).astype(int)), tuple(np.round(q).astype(int)), color, 2 if major else 1)
    return img


def sanity_warnings(H, world_pts, image_size, fov_deg=None):
    """점이 4개뿐이면 오차가 늘 0이라 잘못 입력해도 모른다 → 기하학적으로 말이 안 되는 것을 찾는다."""
    out = []
    for i, (x, y) in enumerate(np.asarray(world_pts, dtype=np.float64), 1):
        ang = math.degrees(math.atan2(x, y))
        if y <= 0:
            out.append(f"point {i} ({x:g}, {y:g}) has y <= 0 = behind the camera. Order is 'x y' (x right +, y away +).")
        elif fov_deg and abs(ang) > fov_deg / 2 + 5:
            hint = " - x and y swapped?" if abs(math.degrees(math.atan2(y, x))) <= fov_deg / 2 + 5 else ""
            out.append(f"point {i} ({x:g}, {y:g}) is {abs(ang):.0f} deg off-axis but the camera sees about "
                       f"+-{fov_deg / 2:.0f} deg (fusion.camera_fov_deg){hint}")
    w, h = image_size
    bottom = project(H, [[w / 2, h - 1]])[0]
    if not np.isfinite(bottom).all() or bottom[1] <= 0:
        out.append("bottom-center of the image maps behind the camera - H is wrong; check the points")
    return out


def dist_m(x, y):
    return math.hypot(x, y)
