"""융합 규칙 시험 (CLAUDE.md 7장): confirmed / camera_only / ghost_suspect / 제외, 조언, TTC."""
import json
from pathlib import Path

import pytest

from vision4iot import calib
from vision4iot.fusion import (CAMERA_ONLY, CONFIRMED, GHOST, CamPerson, FusionParams, fuse, message, ttc_s)
from vision4iot.radar.base import Target

P = FusionParams()


def states(tracks):
    return {t["id"]: t["state"] for t in tracks}


def test_match_within_half_meter_uses_radar_position_and_ttc():
    t = fuse([Target(0, 0.5, 2.0, -1.0)], [CamPerson(7, 0.6, 1.8, "standing", 0.9)], P)
    assert len(t) == 1 and t[0]["state"] == CONFIRMED and t[0]["id"] == 7 and t[0]["radar_id"] == 0
    assert (t[0]["x"], t[0]["y"]) == (0.5, 2.0)                    # 위치는 레이더 값
    assert t[0]["ttc_s"] == pytest.approx(2.06, abs=0.01)           # 2.06 m / 1.0 m/s
    assert t[0]["advice"] == "none"                                 # 서 있으면 조언 없음


def test_crouching_inside_caution_zone_raises():
    t = fuse([Target(0, 0.2, 2.0, 0.0)], [CamPerson(1, 0.25, 2.1, "crouching", 0.8)], P)
    assert t[0]["state"] == CONFIRMED and t[0]["advice"] == "raise" and t[0]["ttc_s"] is None
    far = fuse([Target(0, 0.2, 3.5, 0.0)], [CamPerson(1, 0.2, 3.5, "lying", 0.8)], P)
    assert far[0]["advice"] == "none"                               # 3.0 m 밖이면 올리지 않음


def test_camera_only_person_raises_when_close():
    t = fuse([], [CamPerson(4, -0.9, 2.6, "standing", 0.7)], P)
    assert t[0]["state"] == CAMERA_ONLY and t[0]["advice"] == "raise" and t[0]["ttc_s"] is None
    assert fuse([], [CamPerson(4, 0.0, 3.5)], P)[0]["advice"] == "none"


def test_greedy_one_to_one_nearest_pairs_first():
    radar = [Target(0, 0.0, 2.0), Target(1, 0.4, 2.0)]
    cams = [CamPerson(10, 0.05, 2.0), CamPerson(11, 0.45, 2.0)]
    t = fuse(radar, cams, P)
    assert {(x["id"], x["radar_id"]) for x in t} == {(10, 0), (11, 1)}


def test_no_ghost_beyond_caution_distance():
    assert fuse([Target(0, 0.0, 3.2)], [], P) == []                 # 3 m 밖은 유령이라 하지 않음 (TTC 경고를 낮추지 않게)
    assert fuse([Target(0, 0.0, 2.9)], [], P)[0]["state"] == GHOST


def test_ghost_needs_no_person_within_1_5m_in_view_and_camera_ok():
    radar = [Target(2, 1.2, 2.4)]
    t = fuse(radar, [], P)
    assert t[0]["state"] == GHOST and t[0]["id"] == 102 and t[0]["advice"] == "lower_to_caution"
    assert t[0]["posture"] is None and t[0]["conf"] == 0.0
    assert fuse(radar, [], P, cam_ok=False) == []                   # 카메라 고장이면 유령이라 하지 않음
    assert fuse(radar, [], P, in_view=lambda x, y: False) == []      # 화면 밖이면 판단 안 함
    assert fuse(radar, [CamPerson(1, 0.2, 1.6)], P) == [             # 1.28 m 안에 사람 → 유령 아님, 사람은 camera_only
        {"id": 1, "state": CAMERA_ONLY, "x": 0.2, "y": 1.6, "dist_m": 1.61, "ttc_s": None,
         "posture": None, "conf": 0.0, "advice": "raise"}]


def test_ambiguous_between_half_and_one_and_half_meters_is_dropped_for_radar():
    t = fuse([Target(0, 0.0, 2.0)], [CamPerson(1, 1.0, 2.0)], P)    # 1.0 m 떨어짐: 짝도 유령도 아님
    assert states(t) == {1: CAMERA_ONLY}


def test_camera_person_near_a_radar_target_taken_by_someone_else_is_dropped():
    radar = [Target(0, 0.0, 2.0)]
    cams = [CamPerson(1, 0.0, 2.05), CamPerson(2, 0.3, 2.0)]        # 둘 다 0.5 m 안, 짝은 하나뿐
    assert states(fuse(radar, cams, P)) == {1: CONFIRMED}


def test_ttc_only_when_closing():
    assert ttc_s(2.0, -0.5) == 4.0
    assert ttc_s(2.0, 0.3) is None and ttc_s(2.0, None) is None and ttc_s(0, -1) is None


def test_message_shape_matches_spec():
    m = message(1000.0, 5, True, [], radar_ok=False, now=1000.142)
    assert m == {"ts": 1000.0, "frame": 5, "cam_ok": True, "latency_ms": 142, "tracks": [], "radar_ok": False}
    json.dumps(m)


def test_in_view_uses_calibration():
    p = Path(__file__).resolve().parents[1] / "calib" / "H_c270.json"
    cal = calib.load(p)
    if cal is None:
        pytest.skip("C270 calibration file not on this machine")
    assert cal.in_view(0.5, 1.5) and cal.in_view(0.0, 2.0)
    assert not cal.in_view(0.0, 0.2)      # 화면 아래보다 가까움
    assert not cal.in_view(5.0, 1.0)      # 옆으로 화면 밖
    assert not cal.in_view(0.0, -2.0)     # 카메라 뒤
