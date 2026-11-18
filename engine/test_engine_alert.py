"""엔진이 실제 alert(/AE-forklift01/alert)를 쓰는 모드: 카메라 결합 판단이 지게차 동작까지 이어지는지 확인한다."""

import json
import time
import unittest

from engine.config import RiskConfig
from engine.main import RiskApplication
from engine.onem2m_http import HTTPAlertWriter
from engine.risk_engine import RiskEngine


class FakeHTTP:
    """OneM2MHTTP 대역: events·alert 기록과 최신 Vision CIN 조회만 흉내 낸다."""

    def __init__(self):
        self.posts, self.vision = [], None

    def create_event_cin(self, event):
        return self.create_cin("/AE-riskengine/events", event)

    def create_cin(self, path, event):
        self.posts.append((path, event))
        return {}

    def get_latest_cin(self, path):
        return {"m2m:cin": {"ri": "v", "con": json.dumps({**self.vision, "ts": time.time()})}}, None

    def alerts(self):
        return [e["level"] for p, e in self.posts if p == "/AE-forklift01/alert"]


def frame(ri, x_mm, y_mm):
    return {"m2m:cin": {"ri": ri, "con": json.dumps({"ts": 1, "targets": [{"slot": 0, "x": x_mm, "y": y_mm}]})}}


class EngineAlertTest(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.http = FakeHTTP()
        self.http.vision = {"cam_ok": True, "radar_ok": True, "tracks": []}
        self.app = RiskApplication(self.http, RiskEngine(RiskConfig(release_hold_s=0), clock=lambda: self.now[0]),
                                   alert_writer=HTTPAlertWriter(self.http, "/AE-forklift01/alert"),
                                   vision_path="/AE-VisionAI/fusedTracks/la")

    def step(self, ri, x_mm, y_mm):
        self.now[0] += 0.5
        return self.app.accept_message(frame(ri, x_mm, y_mm), self.now[0], dedupe=True)

    def test_distance_levels_reach_the_forklift_alert(self):
        self.step("a", 0, 2000)      # 멀리 서 있음
        self.step("b", 0, 2000)
        self.step("c", 0, 900)       # 1.0 m 안 → warn
        self.step("d", 0, 900)
        self.step("e", 0, 400)       # 0.5 m 안 → danger(지게차 정지)
        self.assertEqual(self.http.alerts()[0], "safe")
        self.assertIn("warn", self.http.alerts())
        self.assertEqual(self.http.alerts()[-1], "danger")
        last_alert = [e for path, e in self.http.posts if path == "/AE-forklift01/alert"][-1]
        self.assertEqual(last_alert, {"level": "danger", "dist": 400, "ttc": None})

    def test_camera_only_person_raises_the_forklift_alert(self):
        self.step("a", 0, 2000)
        self.step("b", 0, 2000)
        self.assertEqual(self.http.alerts(), ["safe"])
        # 레이더는 안전인데 카메라가 레이더가 놓친 사람을 봄 → 지게차 경보도 warn
        self.http.vision = {"cam_ok": True, "radar_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}
        self.step("c", 0, 2000)
        self.assertEqual(self.http.alerts(), ["safe", "warn"])

    def test_vision_without_radar_input_is_not_trusted(self):
        self.step("a", 0, 2000)
        self.http.vision = {"cam_ok": True, "radar_ok": False, "tracks": [{"state": "camera_only", "advice": "raise"}]}
        self.step("b", 0, 2000)
        self.assertEqual(self.http.alerts(), ["safe"])

    def test_radar_silence_stops_the_forklift(self):
        self.step("a", 0, 2000)
        self.now[0] += 5
        self.assertEqual(self.app.tick()["status"], "UNKNOWN")
        self.assertEqual(self.http.alerts()[-1], "unknown")


if __name__ == "__main__":
    unittest.main()
