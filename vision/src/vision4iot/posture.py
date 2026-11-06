"""관절로 자세 판정: standing / crouching / lying / None + 최근 N프레임 다수결 (CLAUDE.md 8장).

판정 순서: lying → crouching → standing. 근거가 부족하면 None(애매하면 판단하지 않는다, 4장).
- lying:     몸통(어깨 중점→엉덩이 중점)이 수직에서 lying_torso_deg 이상, 또는 박스 가로/세로 > lying_box_ratio
             (박스가 화면 가장자리에 닿아 잘렸으면 박스 비율은 쓰지 않는다 — 상반신만 보여도 박스가 넓어지므로)
- crouching: (엉덩이–발목 세로 거리)/(어깨–엉덩이 길이) < crouch_hip_ankle_ratio, 또는 무릎 각도 < crouch_knee_deg
- standing:  몸통이 보이고, 다리 값(비율·무릎 각도) 중 하나 이상을 계산할 수 있고, 둘 다 crouching이 아님
"""
import math
from collections import Counter, deque
from dataclasses import dataclass

import numpy as np

# COCO 키포인트 번호
L_SHOULDER, R_SHOULDER = 5, 6
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

STANDING, CROUCHING, LYING = "standing", "crouching", "lying"
SEVERITY = {None: 0, STANDING: 1, CROUCHING: 2, LYING: 3}   # 다수결 동점이면 더 위험한 쪽 (raise는 자유, 4장)


@dataclass
class PostureParams:
    kp_min_conf: float = 0.3
    lying_torso_deg: float = 60
    lying_box_ratio: float = 1.2
    edge_margin_px: float = 5       # 박스가 화면 끝에서 이만큼 안이면 "잘림"
    crouch_hip_ankle_ratio: float = 0.9
    crouch_knee_deg: float = 110
    vote_frames: int = 5

    @classmethod
    def from_cfg(cls, cfg):
        return cls(**{k: cfg[k] for k in cls.__dataclass_fields__ if k in cfg})


@dataclass
class PostureResult:
    label: str | None
    torso_deg: float | None = None        # 몸통의 수직 대비 각도
    box_ratio: float | None = None        # 박스 가로/세로
    box_cut: bool = False                 # 박스가 화면 가장자리에 닿음 → box_ratio를 판정에 안 씀
    hip_ankle_ratio: float | None = None  # (엉덩이–발목 세로 거리)/(어깨–엉덩이 길이)
    knee_deg: float | None = None         # 보이는 무릎 중 작은 각도

    def debug_text(self):
        def f(v, unit=""):
            return "-" if v is None else f"{v:.0f}{unit}" if unit else f"{v:.2f}"
        return (f"torso {f(self.torso_deg, 'deg')} box {f(self.box_ratio)}{' cut' if self.box_cut else ''} "
                f"h/a {f(self.hip_ankle_ratio)} knee {f(self.knee_deg, 'deg')}")


def _mid(kpts, ok, idxs):
    pts = [kpts[i, :2] for i in idxs if ok[i]]
    return np.mean(pts, axis=0) if pts else None


def _angle(a, b, c):
    """b에서 a–b–c가 이루는 각도(도)."""
    v1, v2 = a - b, c - b
    n = np.linalg.norm(v1) * np.linalg.norm(v2)
    if n < 1e-6:
        return None
    return math.degrees(math.acos(np.clip(np.dot(v1, v2) / n, -1.0, 1.0)))


def measure(kpts, box, p, frame_size=None):
    """판정에 쓰는 값만 계산한다(라벨 없음). frame_size = (w, h), 없으면 잘림 검사 안 함."""
    kpts = np.asarray(kpts, dtype=float)
    ok = kpts[:, 2] >= p.kp_min_conf
    r = PostureResult(None)

    x1, y1, x2, y2 = box
    if y2 - y1 > 0:
        r.box_ratio = (x2 - x1) / (y2 - y1)
    if frame_size is not None:
        w, h = frame_size
        m = p.edge_margin_px
        r.box_cut = bool(x1 <= m or y1 <= m or x2 >= w - m or y2 >= h - m)

    shoulder = _mid(kpts, ok, (L_SHOULDER, R_SHOULDER))
    hip = _mid(kpts, ok, (L_HIP, R_HIP))
    ankle = _mid(kpts, ok, (L_ANKLE, R_ANKLE))

    torso_len = None
    if shoulder is not None and hip is not None:
        dx, dy = hip - shoulder
        torso_len = math.hypot(dx, dy)
        if torso_len > 1e-6:
            r.torso_deg = math.degrees(math.atan2(abs(dx), dy))   # 0 = 똑바로 섬, 90 = 수평

    if hip is not None and ankle is not None and torso_len and torso_len > 1e-6:
        r.hip_ankle_ratio = (ankle[1] - hip[1]) / torso_len

    knees = []
    for h, k, a in ((L_HIP, L_KNEE, L_ANKLE), (R_HIP, R_KNEE, R_ANKLE)):
        if ok[h] and ok[k] and ok[a]:
            ang = _angle(kpts[h, :2], kpts[k, :2], kpts[a, :2])
            if ang is not None:
                knees.append(ang)
    if knees:
        r.knee_deg = min(knees)
    return r


def classify(kpts, box, p, frame_size=None):
    r = measure(kpts, box, p, frame_size)
    if (r.torso_deg is not None and r.torso_deg >= p.lying_torso_deg) or \
       (r.box_ratio is not None and not r.box_cut and r.box_ratio > p.lying_box_ratio):
        r.label = LYING
    elif r.torso_deg is None:
        r.label = None                     # 몸통이 안 보이면 앉았는지 섰는지 모른다
    elif (r.hip_ankle_ratio is not None and r.hip_ankle_ratio < p.crouch_hip_ankle_ratio) or \
         (r.knee_deg is not None and r.knee_deg < p.crouch_knee_deg):
        r.label = CROUCHING
    elif r.hip_ankle_ratio is not None or r.knee_deg is not None:
        r.label = STANDING
    else:
        r.label = None                     # 다리가 안 보임
    return r


def majority(labels):
    """최빈값. 동점이면 더 위험한 자세. None도 한 표."""
    if not labels:
        return None
    counts = Counter(labels)
    return max(counts, key=lambda k: (counts[k], SEVERITY[k]))


class PostureVoter:
    """추적 id별 최근 vote_frames 프레임 다수결."""

    def __init__(self, vote_frames=5, forget_after=30):
        self.n = vote_frames
        self.forget_after = forget_after
        self.hist = {}       # id -> deque[label]
        self.last_seen = {}  # id -> frame 번호
        self.frame = 0

    def update(self, track_id, label):
        if track_id is None:          # 추적 id가 없으면 이번 판정 그대로
            return label
        h = self.hist.setdefault(track_id, deque(maxlen=self.n))
        h.append(label)
        self.last_seen[track_id] = self.frame
        return majority(list(h))

    def next_frame(self):
        """프레임마다 한 번. 오래 안 보인 id 기록을 지운다."""
        self.frame += 1
        for tid in [t for t, f in self.last_seen.items() if self.frame - f > self.forget_after]:
            del self.hist[tid], self.last_seen[tid]
