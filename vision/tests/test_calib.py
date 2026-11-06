"""호모그래피 보정 시험 — 알려진 카메라(H)로 가짜 보정점을 만들어 되찾는다."""
import json

import numpy as np
import pytest

from vision4iot import calib

# 바닥 m → 화면 px 로 보내는 "진짜" 투영 (640x480, 카메라가 바닥을 비스듬히 내려다봄)
WORLD_TO_IMG = np.array([[160.0, 40.0, 320.0],
                         [0.0, -30.0, 600.0],
                         [0.0, 0.25, 1.0]])
IMG_TO_WORLD = np.linalg.inv(WORLD_TO_IMG)
WORLD = np.array([[-1.0, 1.0], [1.0, 1.0], [-1.0, 3.0], [1.0, 3.0], [0.0, 2.0], [0.5, 4.0]])


def to_img(world):
    return calib.project(WORLD_TO_IMG, world)


def test_fit_recovers_floor_coordinates():
    H, err = calib.fit_homography(to_img(WORLD), WORLD)
    assert err["mean"] < 1e-6 and err["max"] < 1e-6
    probe = np.array([[0.3, 2.7], [-0.8, 1.5]])        # 보정점이 아닌 곳
    assert calib.project(H, to_img(probe)) == pytest.approx(probe, abs=1e-6)


def test_reprojection_error_reports_bad_measurement():
    world = WORLD.copy()
    world[5] += (0.2, 0.0)                            # 한 점을 20cm 잘못 잼
    _, err = calib.fit_homography(to_img(WORLD), world)
    assert err["max"] > 0.05
    assert len(err["per_point"]) == len(WORLD)


def test_needs_four_points():
    with pytest.raises(ValueError):
        calib.fit_homography(to_img(WORLD[:3]), WORLD[:3])


def test_save_and_load_roundtrip(tmp_path):
    img = to_img(WORLD)
    H, err = calib.fit_homography(img, WORLD)
    path = tmp_path / "calib" / "H.json"
    calib.save(path, H, img, WORLD, err, (640, 480), note="test")
    d = json.loads(path.read_text(encoding="utf-8"))
    assert {"H", "date", "reproj_err_m", "image_size", "points"} <= d.keys()
    assert "+" in d["date"] or "Z" in d["date"]       # 시간대 포함
    c = calib.load(path)
    assert c.image_size == (640, 480)
    assert c.to_floor(to_img([[0.3, 2.7]]))[0] == pytest.approx([0.3, 2.7], abs=1e-6)


def test_load_missing_returns_none(tmp_path):
    assert calib.load(tmp_path / "nope.json") is None


def test_scaled_frame_size():
    H, _ = calib.fit_homography(to_img(WORLD), WORLD)
    c = calib.Calib(H, (640, 480))
    px_1280 = to_img([[0.3, 2.7]]) * 2                # 같은 장면을 2배 해상도로
    assert c.to_floor(px_1280, (1280, 960))[0] == pytest.approx([0.3, 2.7], abs=1e-6)
    assert "scaled" in c.check_frame_size((1280, 960))
    assert "aspect" in c.check_frame_size((640, 360))
    assert c.check_frame_size((640, 480)) is None


def test_sanity_ok_for_good_points():
    H, _ = calib.fit_homography(to_img(WORLD), WORLD)
    # 시험용 카메라의 보정점은 최대 45° → 광각(102°, Camera Module 3 Wide) 기준
    assert calib.sanity_warnings(H, WORLD, (640, 480), fov_deg=102) == []


def test_sanity_catches_swapped_xy_like_real_mistake():
    # 2026-10-31 실제 보정: 점 1을 "0.83 0.33"으로 입력(원래 0.33 0.83) → 4점이라 오차 0인데 H가 엉망
    px = [(580, 452), (86, 392), (385, 360), (253, 329)]
    world = [(0.83, 0.33), (-0.44, 1.18), (0.21, 1.17), (-0.24, 1.84)]
    H, err = calib.fit_homography(px, world)
    assert err["max"] < 1e-6                              # 오차로는 못 잡는다
    warns = calib.sanity_warnings(H, world, (640, 480), fov_deg=66)
    assert any("point 1" in w and "swapped" in w for w in warns)
    assert any("behind the camera" in w for w in warns)
    fixed = [(0.33, 0.83)] + world[1:]
    H2, _ = calib.fit_homography(px, fixed)
    assert calib.sanity_warnings(H2, fixed, (640, 480), fov_deg=66) == []


def test_sanity_flags_negative_y():
    H, _ = calib.fit_homography(to_img(WORLD), WORLD)
    assert any("y <= 0" in w for w in calib.sanity_warnings(H, [(0.2, -1.0)], (640, 480)))


def kpts_with_ankles(left, right, conf=0.9):
    k = np.zeros((17, 3))
    if left:
        k[15] = (*left, conf)
    if right:
        k[16] = (*right, conf)
    return k


def test_foot_point_ankle_x_and_box_bottom_y():
    # 좌우는 발목 중점, 앞뒤는 박스 맨 아래 (발목은 바닥에서 떠 있어 멀게 나옴, 8장·11/6 실측)
    fp, src = calib.foot_point(kpts_with_ankles((100, 400), (140, 410)), (80, 100, 170, 420))
    assert src == "feet"
    assert fp == pytest.approx([120, 420])


def test_foot_point_falls_back_to_box_bottom():
    # 발목 하나만 보이거나 신뢰도가 낮으면 박스 아래 중앙
    for k in (kpts_with_ankles((100, 400), None), kpts_with_ankles((100, 400), (140, 410), conf=0.1)):
        fp, src = calib.foot_point(k, (80, 100, 160, 420), frame_size=(640, 480))
        assert src == "box"
        assert fp == pytest.approx([120, 420])


def test_foot_point_flags_box_cut_at_bottom():
    fp, src = calib.foot_point(np.zeros((17, 3)), (80, 100, 160, 479), frame_size=(640, 480))
    assert src == "box_cut"
    # 박스가 잘렸어도 발목이 보이면 발목 중점 (박스 아래는 발이 아님)
    fp, src = calib.foot_point(kpts_with_ankles((100, 470), (140, 472)), (80, 100, 160, 479), frame_size=(640, 480))
    assert src == "box_cut" and fp == pytest.approx([120, 471])
