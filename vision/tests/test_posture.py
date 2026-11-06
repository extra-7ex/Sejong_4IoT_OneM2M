"""자세 판정 시험 — 가짜 COCO 키포인트(화면 px, y는 아래로 증가)."""
import numpy as np
import pytest

from vision4iot.posture import (CROUCHING, LYING, STANDING, PostureParams, PostureVoter,
                                classify, majority)

P = PostureParams()


def make(points, conf=0.9):
    """{키포인트 번호: (x, y)} → (17, 3). 없는 점은 신뢰도 0."""
    k = np.zeros((17, 3))
    for i, (x, y) in points.items():
        k[i] = (x, y, conf)
    return k


def box_of(k, pad=10):
    v = k[k[:, 2] > 0, :2]
    return (v[:, 0].min() - pad, v[:, 1].min() - pad, v[:, 0].max() + pad, v[:, 1].max() + pad)


# 서 있음: 어깨 100 → 엉덩이 200 → 무릎 300 → 발목 400, 다리 곧게
STAND = make({0: (110, 60), 5: (90, 100), 6: (130, 100), 11: (95, 200), 12: (125, 200),
              13: (95, 300), 14: (125, 300), 15: (95, 400), 16: (125, 400)})

# 쭈그림: 엉덩이와 발목 높이 차가 작고 무릎이 앞으로 접힘
CROUCH = make({0: (110, 160), 5: (90, 200), 6: (130, 200), 11: (95, 300), 12: (125, 300),
               13: (150, 290), 14: (170, 290), 15: (100, 360), 16: (130, 360)})

# 누움: 몸이 가로로
LIE = make({0: (40, 300), 5: (80, 290), 6: (80, 320), 11: (200, 290), 12: (200, 320),
            13: (300, 290), 14: (300, 320), 15: (400, 290), 16: (400, 320)})


def test_standing():
    r = classify(STAND, box_of(STAND), P)
    assert r.label == STANDING
    assert r.torso_deg == pytest.approx(0, abs=1)
    assert r.hip_ankle_ratio == pytest.approx(2.0, abs=0.01)
    assert r.knee_deg == pytest.approx(180, abs=1)


def test_crouching():
    r = classify(CROUCH, box_of(CROUCH), P)
    assert r.label == CROUCHING
    assert r.hip_ankle_ratio < P.crouch_hip_ankle_ratio
    assert r.knee_deg < P.crouch_knee_deg


def test_lying_by_torso_angle():
    r = classify(LIE, box_of(LIE), P)
    assert r.label == LYING
    assert r.torso_deg == pytest.approx(90, abs=1)


def test_lying_by_box_ratio_only():
    # 몸통은 서 있는 모양이어도 박스가 가로로 길면 lying (8장 규칙의 "또는")
    r = classify(STAND, (0, 0, 300, 200), P)
    assert r.label == LYING


def test_box_ratio_ignored_when_box_is_cut_at_frame_edge():
    # 상반신만 보여 박스가 화면 아래 끝에 닿음: 비율 1.5여도 lying이 아니다 (8장)
    upper = make({0: (320, 200), 5: (240, 340), 6: (400, 340)})   # 얼굴·어깨만
    box = (80, 150, 560, 480)                                      # 640x480 화면 아래 끝까지
    r = classify(upper, box, P, frame_size=(640, 480))
    assert r.box_ratio > P.lying_box_ratio and r.box_cut
    assert r.label is None
    # 같은 박스라도 화면 안에 다 들어오면 비율 규칙이 그대로 적용된다
    assert classify(upper, box, P, frame_size=(1280, 960)).label == LYING


def test_torso_angle_still_works_when_box_is_cut():
    assert classify(LIE, (0, 270, 420, 340), P, frame_size=(640, 480)).label == LYING


def test_crouching_by_knee_angle_only():
    # 엉덩이–발목 비율은 정상이지만 무릎이 꺾였으면 crouching
    k = STAND.copy()
    k[13, :2] = (200, 300)     # 왼 무릎만 앞으로 (약 87°)
    r = classify(k, box_of(k), P)
    assert r.hip_ankle_ratio >= P.crouch_hip_ankle_ratio
    assert r.label == CROUCHING


def test_null_without_torso():
    k = make({0: (110, 60), 1: (105, 55), 2: (115, 55)})   # 얼굴만
    assert classify(k, (90, 40, 130, 200), P).label is None


def test_null_without_legs():
    k = STAND.copy()
    k[13:17, 2] = 0             # 무릎·발목 안 보임
    assert classify(k, (80, 50, 140, 210), P).label is None


def test_low_confidence_points_are_ignored():
    k = STAND.copy()
    k[13:17, 2] = 0.1           # kp_min_conf(0.3)보다 낮음 → 다리 없음과 같다
    assert classify(k, (80, 50, 140, 210), P).label is None


def test_thresholds_come_from_params():
    strict = PostureParams(crouch_hip_ankle_ratio=2.5)   # 서 있는 비율 2.0도 쭈그림으로
    assert classify(STAND, box_of(STAND), strict).label == CROUCHING


def test_params_from_config_dict():
    p = PostureParams.from_cfg({"kp_min_conf": 0.5, "vote_frames": 7, "unknown": 1})
    assert p.kp_min_conf == 0.5 and p.vote_frames == 7


def test_majority_ties_go_to_more_severe():
    assert majority([STANDING, STANDING, CROUCHING, CROUCHING]) == CROUCHING
    assert majority([STANDING, STANDING, STANDING, LYING, LYING]) == STANDING
    assert majority([None, STANDING]) == STANDING
    assert majority([]) is None


def test_voter_window_and_ids():
    v = PostureVoter(vote_frames=5)
    for label in [STANDING] * 5:
        out = v.update(1, label)
    assert out == STANDING
    for label in [CROUCHING] * 2:
        out = v.update(1, label)
    assert out == STANDING                  # 5개 중 3개가 아직 standing
    out = v.update(1, CROUCHING)
    assert out == CROUCHING                 # 3:2로 뒤집힘
    assert v.update(2, LYING) == LYING      # 다른 id는 따로
    assert v.update(None, CROUCHING) == CROUCHING   # id 없으면 그대로


def test_voter_forgets_old_ids():
    v = PostureVoter(vote_frames=5, forget_after=3)
    v.update(1, LYING)
    for _ in range(4):
        v.next_frame()
    assert 1 not in v.hist
