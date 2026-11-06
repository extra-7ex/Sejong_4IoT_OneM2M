"""레이더 공통 형식·시뮬레이터 시험 (CLAUDE.md 9장·13장)."""
import json
import random

import pytest

from vision4iot.radar.base import Target, from_team_con, to_team_con
from vision4iot.radar.sim import DEFAULT_SCRIPT, RadarSim

T0 = 1_762_300_000.0


def test_team_con_units_mm_cms_and_empty_targets():
    con = to_team_con([Target(0, 0.3731, 2.0, -0.85)], T0 + 0.12345, src="sim")
    assert con == {"ts": round(T0 + 0.123, 3), "targets": [{"x": 373, "y": 2000, "v": -85}], "src": "sim"}
    assert to_team_con([], T0) == {"ts": T0, "targets": []}          # 사람이 없어도 targets: []


def test_team_con_flip_and_round_trip():
    t = [Target(0, 0.5, 1.5, -0.4), Target(1, -1.2, 3.0, 0.0)]
    con = to_team_con(t, T0, flip_x=True, flip_v=True)
    assert con["targets"][0] == {"x": -500, "y": 1500, "v": 40}
    ts, back = from_team_con(json.dumps(con), flip_x=True, flip_v=True)   # JSON 문자열도 받는다
    assert ts == T0
    assert [(b.id, b.x, b.y, b.v) for b in back] == [(0, 0.5, 1.5, -0.4), (1, -1.2, 3.0, 0.0)]


def test_team_con_keeps_at_most_three_targets():
    t = [Target(i, 0, 1 + i) for i in range(5)]
    assert len(to_team_con(t, T0)["targets"]) == 3


def at(sim, s):
    return sim.get_targets(T0 + s)


def test_default_script_walks_in_dangerous_then_leaves_then_empty():
    sim = RadarSim("script")
    assert sim.scenario_name == "default"
    first = at(sim, 0)                       # 첫 호출 시각이 시나리오 0초
    assert [t.id for t in first] == [0] and first[0].dist == pytest.approx(5.59, abs=0.01)
    approach = at(sim, 5)
    assert approach[0].v < -0.3              # 다가오면 v < 0
    standing = {t.id: t for t in at(sim, 12)}
    assert standing[0].dist == pytest.approx(1.02, abs=0.01) and standing[0].v == pytest.approx(0, abs=1e-6)
    assert 1 in standing                      # 멀리 서 있는 두 번째 사람
    assert at(sim, 17)[0].v > 0              # 떠나면 v > 0
    assert at(sim, 25) == []                 # 아무도 없음
    assert at(sim, 30 + 12)[0].dist == pytest.approx(1.02, abs=0.01)   # 30초마다 반복


def test_targets_sorted_nearest_first_and_ghost_added():
    sim = RadarSim("ghost", ghost_points=[[1.6, 3.1]])
    at(sim, 0)                               # 시나리오 시작
    out = at(sim, 12)
    assert [t.id for t in out] == [0, 100, 1]          # 1.02m, 3.49m(유령), 4.72m
    assert out[1].x == 1.6 and out[1].v == 0


def test_script_file_used_when_present(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"tracks": [{"id": 7, "points": [[0, 0, 2], [10, 0, 1]]}]}), encoding="utf-8")
    sim = RadarSim.from_cfg({"mode": "script", "script_file": str(p)})
    assert sim.scenario_name == "file"
    assert at(sim, 0)[0].id == 7 and at(sim, 5)[0].y == pytest.approx(1.5)
    assert at(sim, 11) == []                 # loop_s 없으면 반복하지 않음
    missing = RadarSim.from_cfg({"mode": "script", "script_file": str(tmp_path / "none.json")})
    assert missing.script is DEFAULT_SCRIPT


def test_from_camera_adds_noise_and_drops_some_static_people():
    sim = RadarSim("from_camera", noise_m=0.15, drop_static_prob=0.6, rng=random.Random(1))
    walking = [Target(3, 1.0, 2.0, -0.8)]
    out = [sim.get_targets(T0, walking)[0] for _ in range(200)]
    assert all(abs(t.x - 1.0) <= 0.15 and abs(t.y - 2.0) <= 0.15 for t in out)
    assert len({round(t.x, 4) for t in out}) > 50                       # 정말 흔들린다
    static = [Target(4, 0.0, 2.0, 0.0)]
    kept = sum(bool(sim.get_targets(T0 + s, static)) for s in range(1000))   # 1초마다 다시 정함
    assert 300 < kept < 500                                             # 약 40%만 남음
    assert sim.get_targets(T0, None) == []


def test_from_camera_drop_is_sticky_within_a_second_and_speed_is_estimated():
    sim = RadarSim("from_camera", noise_m=0.0, drop_static_prob=1.0, rng=random.Random(2))
    still = [sim.get_targets(T0 + i * 0.1, [Target(9, 0.0, 2.0, 0.0)]) for i in range(5)]
    assert all(s == [] for s in still)                                  # 가만히 있으면 계속 놓침 (깜빡이지 않음)
    walk = []
    for i in range(30):                                                 # 0.1초마다 5 cm씩 다가옴 = 0.5 m/s
        walk = sim.get_targets(T0 + 10 + i * 0.1, [Target(9, 0.0, 3.0 - 0.05 * i, 0.0)])
    assert walk and walk[0].v == pytest.approx(-0.5, abs=0.05)          # 움직이면 잡히고 속도도 추정


def test_unknown_mode_rejected():
    with pytest.raises(ValueError):
        RadarSim("nope")
