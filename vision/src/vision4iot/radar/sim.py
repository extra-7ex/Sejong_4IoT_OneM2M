"""레이더 시뮬레이터 (CLAUDE.md 13장). 실제 레이더가 아니다 → 결과를 쓰는 쪽은 반드시 "sim"으로 표시한다.

모드 (config `radar.sim.mode`)
- script:      경로 [시각 s, x m, y m]를 따라 표적이 움직인다. 파일(`script_file`)이 없으면 DEFAULT_SCRIPT.
- ghost:       script + 고정 위치의 가짜 표적(`ghost_points`, 금속 선반 반사 흉내). 카메라엔 사람이 없는 자리.
- from_camera: 카메라가 본 사람 위치(Target 목록)에 잡음을 더해 표적으로. 거의 안 움직이는 사람은
               확률적으로 빠뜨린다(레이더 약점 흉내). 융합 단계에서 쓴다.
속도 v는 레이더처럼 "레이더 쪽 방향 속도"(거리의 변화율, 다가오면 음수)로 만든다.
"""
import json
import math
import random
from pathlib import Path

from vision4iot.radar.base import MAX_TARGETS, Target

# 기본 시나리오(30초 반복): 한 사람이 5.5m에서 1.0m까지 다가와 3초 서 있다 떠나고(SAFE→WARNING→DANGER→…),
# 다른 사람은 4.7m 거리에 잠깐 서 있다(SAFE). 마지막 10초는 아무도 없다(targets: []).
DEFAULT_SCRIPT = {
    "loop_s": 30,
    "tracks": [
        {"id": 0, "points": [[0, 1.0, 5.5], [8, 0.3, 2.0], [11, 0.2, 1.0], [14, 0.2, 1.0], [20, 1.2, 5.5]]},
        {"id": 1, "points": [[3, -2.5, 4.0], [12, -2.5, 4.0]]},
    ],
}

_DV_DT = 0.05   # 속도 계산용 시간 간격(s)


def _pos(points, t):
    """경로 위 t초의 (x, y). 경로 밖이면 None."""
    if not points or t < points[0][0] or t > points[-1][0]:
        return None
    for (t0, x0, y0), (t1, x1, y1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            a = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return x0 + a * (x1 - x0), y0 + a * (y1 - y0)
    return points[0][1], points[0][2]       # 점이 하나뿐인 경로


def _radial_speed(points, t):
    """거리의 변화율(m/s). 경로 끝에서는 안쪽 한쪽 차분."""
    ta, tb = max(points[0][0], t - _DV_DT), min(points[-1][0], t + _DV_DT)
    if tb <= ta:
        return 0.0
    (xa, ya), (xb, yb) = _pos(points, ta), _pos(points, tb)
    return (math.hypot(xb, yb) - math.hypot(xa, ya)) / (tb - ta)


def load_script(path):
    """JSON 시나리오 파일. 없으면 None."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class RadarSim:
    def __init__(self, mode="script", script=None, ghost_points=(), noise_m=0.15,
                 drop_static_prob=0.6, static_speed_mps=0.1, rng=None):
        if mode not in ("script", "ghost", "from_camera"):
            raise ValueError(f"unknown sim mode: {mode}")
        self.mode = mode
        self.script = script or DEFAULT_SCRIPT
        self.ghost_points = [tuple(p) for p in ghost_points]
        self.noise_m = noise_m
        self.drop_static_prob = drop_static_prob
        self.static_speed_mps = static_speed_mps
        self.rng = rng or random.Random()
        self.t0 = None
        self._seen = {}          # from_camera: 사람 id → [x, y, ts, v_추정, 놓침 여부, 결정 시각]

    @classmethod
    def from_cfg(cls, sim_cfg, resolve=lambda p: p, rng=None):
        script = load_script(resolve(sim_cfg["script_file"])) if sim_cfg.get("script_file") else None
        return cls(mode=sim_cfg.get("mode", "script"), script=script,
                   ghost_points=sim_cfg.get("ghost_points", ()), noise_m=sim_cfg.get("noise_m", 0.15),
                   drop_static_prob=sim_cfg.get("drop_static_prob", 0.6),
                   static_speed_mps=sim_cfg.get("static_speed_mps", 0.1), rng=rng)

    @property
    def scenario_name(self):
        return "default" if self.script is DEFAULT_SCRIPT else "file"

    def _script_targets(self, ts):
        if self.t0 is None:
            self.t0 = ts
        loop = self.script.get("loop_s")
        t = ts - self.t0
        if loop:
            t %= loop
        out = []
        for tr in self.script["tracks"]:
            pts = tr["points"]
            if (p := _pos(pts, t)) is not None:
                out.append(Target(tr["id"], p[0], p[1], _radial_speed(pts, t)))
        return out

    def _from_camera(self, people, ts):
        """속도는 주어지면 그대로, 0이면 같은 id의 이전 위치로 추정(거리 변화율, 부드럽게).
        거의 안 움직이는 사람을 놓칠지는 사람마다 1초에 한 번만 정한다 — 실제 레이더도 프레임마다 깜빡이지 않는다."""
        out = []
        for p in people or ():
            s = self._seen.get(p.id)
            v = p.v
            if not v and s is not None and ts > s[2]:
                inst = (math.hypot(p.x, p.y) - math.hypot(s[0], s[1])) / (ts - s[2])
                v = 0.7 * s[3] + 0.3 * inst
            drop, decided = (s[4], s[5]) if s is not None else (False, None)
            if decided is None or ts - decided >= 1.0:
                drop = abs(v) < self.static_speed_mps and self.rng.random() < self.drop_static_prob
                decided = ts
            self._seen[p.id] = [p.x, p.y, ts, v, drop, decided]
            if drop:
                continue
            n = self.noise_m
            out.append(Target(p.id, p.x + self.rng.uniform(-n, n), p.y + self.rng.uniform(-n, n), round(v, 3)))
        return out

    def get_targets(self, ts, people=None):
        """ts(Unix 초)의 표적 목록. from_camera 모드는 people(카메라 Target 목록)이 필요하다.
        LD2450처럼 최대 3개, 가까운 순."""
        if self.mode == "from_camera":
            out = self._from_camera(people, ts)
        else:
            out = self._script_targets(ts)
            if self.mode == "ghost":
                out += [Target(100 + i, x, y, 0.0) for i, (x, y) in enumerate(self.ghost_points)]
        return sorted(out, key=lambda t: t.dist)[:MAX_TARGETS]
