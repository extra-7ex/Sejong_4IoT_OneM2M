"""레이더 표적 + 카메라 사람 → fusedTracks 한 건 (CLAUDE.md 7장 융합 규칙, 10장 출력 형식).

VisionAI는 조언만 낸다(4장): raise / lower_to_caution / none. 감속·정지 명령은 엔진 몫.
- confirmed     레이더 표적과 카메라 사람이 match_radius(0.5m) 안 → 1:1 짝 (가까운 쌍부터 탐욕)
- camera_only   카메라 사람인데 0.5m 안에 레이더 표적이 없음 (레이더가 놓친 사람, 예: 가만히 쭈그림)
- ghost_suspect 레이더 표적인데 ghost_radius(1.5m) 안에 카메라 사람이 전혀 없고, 그 자리가 카메라 화면 안이며 cam_ok,
                그리고 주의 거리(3.0m) 안일 때만
- 그 밖(0.5–1.5m 애매, 화면 밖, 카메라 고장)은 tracks에서 뺀다 → 엔진이 레이더로 직접 판단
advice: raise = 주의 거리(3.0m) 안이고 (crouching/lying 이거나 camera_only) / lower_to_caution = ghost_suspect / 그 외 none.
좌표는 우리 좌표계(5장, m). confirmed·ghost의 위치·TTC는 레이더 값, camera_only는 카메라 값(TTC 없음).
"""
import math
from dataclasses import dataclass

CONFIRMED, CAMERA_ONLY, GHOST = "confirmed", "camera_only", "ghost_suspect"
RISKY_POSTURES = ("crouching", "lying")
GHOST_ID_BASE = 100          # ghost의 id = 100 + 레이더 슬롯 (카메라 추적 id와 겹치지 않게)


@dataclass
class CamPerson:
    id: int | None           # 카메라 추적 id
    x: float                 # m
    y: float                 # m
    posture: str | None = None
    conf: float = 0.0
    cut: bool = False        # 발이 화면 밖(box_cut) → 실제보다 멀 수 있음


@dataclass
class FusionParams:
    match_radius_m: float = 0.5
    ghost_radius_m: float = 1.5
    caution_dist_m: float = 3.0

    @classmethod
    def from_cfg(cls, fusion_cfg, thresholds):
        return cls(fusion_cfg.get("match_radius_m", 0.5), fusion_cfg.get("ghost_radius_m", 1.5),
                   thresholds.get("caution_dist_m", 3.0))


def _d(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def ttc_s(dist, v):
    """레이더 v(m/s, 다가오면 음수)로 충돌까지 남은 시간. 멀어지거나 멈췄으면 None (6장)."""
    if v is None or v >= 0 or dist <= 0:
        return None
    return round(dist / -v, 2)


def advice_for(state, dist, posture, p):
    if state == GHOST:
        return "lower_to_caution"
    if dist < p.caution_dist_m and (state == CAMERA_ONLY or posture in RISKY_POSTURES):
        return "raise"
    return "none"


def _track(tid, state, x, y, ttc, posture, conf, p, radar_id=None):
    dist = math.hypot(x, y)
    t = {"id": tid, "state": state, "x": round(x, 2), "y": round(y, 2), "dist_m": round(dist, 2), "ttc_s": ttc,
         "posture": posture, "conf": round(float(conf), 2), "advice": advice_for(state, dist, posture, p)}
    if radar_id is not None:
        t["radar_id"] = radar_id
    return t


def fuse(radar, cams, p=None, cam_ok=True, in_view=lambda x, y: True):
    """radar: [Target(id, x, y, v)] (m, m/s), cams: [CamPerson] → tracks(list of dict).
    in_view(x, y): 그 바닥점이 카메라 화면 안인지 (유령 판정에만 씀)."""
    p = p or FusionParams()
    tracks, used_r, used_c = [], set(), set()
    pairs = sorted((_d(r.x, r.y, c.x, c.y), i, j) for i, r in enumerate(radar) for j, c in enumerate(cams))
    for d, i, j in pairs:
        if d > p.match_radius_m:
            break
        if i in used_r or j in used_c:
            continue
        used_r.add(i)
        used_c.add(j)
        r, c = radar[i], cams[j]
        tracks.append(_track(c.id, CONFIRMED, r.x, r.y, ttc_s(r.dist, r.v), c.posture, c.conf, p, r.id))

    for j, c in enumerate(cams):
        if j in used_c:
            continue
        if any(_d(r.x, r.y, c.x, c.y) <= p.match_radius_m for r in radar):
            continue     # 가까운 레이더 표적이 다른 사람과 짝 → 애매, 엔진이 레이더로 판단
        tracks.append(_track(c.id, CAMERA_ONLY, c.x, c.y, None, c.posture, c.conf, p))

    for i, r in enumerate(radar):
        if i in used_r or not cam_ok or not in_view(r.x, r.y):
            continue
        if r.dist >= p.caution_dist_m:
            continue     # 3m 밖은 카메라가 놓칠 수 있고 엔진 경고는 TTC(빠른 접근) 때문 → 낮추지 않는다 (11/6 상희 결정)
        if any(_d(r.x, r.y, c.x, c.y) <= p.ghost_radius_m for c in cams):
            continue     # 근처에 사람이 보임 → 유령이라 할 근거 없음 (애매하면 none, 4장)
        tracks.append(_track(GHOST_ID_BASE + r.id, GHOST, r.x, r.y, ttc_s(r.dist, r.v), None, 0.0, p, r.id))
    return tracks


def message(ts, frame_no, cam_ok, tracks, radar_ok=None, now=None):
    """fusedTracks CIN 한 건(10장). ts = 프레임을 찍은 Unix 초, latency_ms = 보낼 때까지 걸린 시간."""
    m = {"ts": round(ts, 3), "frame": frame_no, "cam_ok": bool(cam_ok),
         "latency_ms": None if now is None else int(round((now - ts) * 1000)), "tracks": tracks}
    if radar_ok is not None:
        m["radar_ok"] = bool(radar_ok)
    return m
