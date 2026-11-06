"""레이더 공통 형식 (CLAUDE.md 5장·9장).

- 안에서는 우리 좌표계: Target(id, x, y, v) — m, m/s, x 오른쪽 +, y 지게차에서 멀어지는 쪽 +, 다가오면 v < 0.
- 팀 radar con(tinyIoT `AE-forklift01/radar`)은 LD2450 원본 단위: `{"ts", "targets": [{"x", "y", "v"}]}` mm, cm/s.
  변환은 이 파일 한 곳에서만 한다. 부호 차이는 config `radar.flip_x`·`flip_v`(기본 false = 그대로).
- 팀 con에는 표적 id가 없다 → 읽을 때는 슬롯 순서(0–2)를 id로 쓴다(잠정, 9장).
"""
import json
import math
from dataclasses import dataclass

MAX_TARGETS = 3   # LD2450은 한 번에 최대 3개


@dataclass(frozen=True)
class Target:
    id: int
    x: float          # m
    y: float          # m
    v: float = 0.0    # m/s, 다가오면 음수

    @property
    def dist(self):
        return math.hypot(self.x, self.y)


def _signs(flip_x, flip_v):
    return (-1 if flip_x else 1), (-1 if flip_v else 1)


def to_team_con(targets, ts, flip_x=False, flip_v=False, src=None):
    """우리 Target 목록 → 팀 radar con(dict). 표적이 없어도 `targets: []`로 만든다(엔진은 1초 넘게 비면 UNKNOWN).
    src(예: "sim")를 주면 con에 그대로 넣는다 — 시뮬레이터 데이터를 숨기지 않기 위해(13장)."""
    sx, sv = _signs(flip_x, flip_v)
    con = {"ts": round(ts, 3),
           "targets": [{"x": round(sx * t.x * 1000), "y": round(t.y * 1000), "v": round(sv * t.v * 100)}
                       for t in targets[:MAX_TARGETS]]}
    if src:
        con["src"] = src
    return con


def from_team_con(con, flip_x=False, flip_v=False):
    """팀 radar con(dict 또는 JSON 문자열) → (ts, [Target]). id는 슬롯 순서."""
    if isinstance(con, str):
        con = json.loads(con)
    sx, sv = _signs(flip_x, flip_v)
    targets = [Target(i, sx * t["x"] / 1000, t["y"] / 1000, sv * t.get("v", 0) / 100)
               for i, t in enumerate(con.get("targets", [])[:MAX_TARGETS])]
    return con.get("ts"), targets
