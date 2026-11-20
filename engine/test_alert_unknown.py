"""레이더 입력이 끊기면 엔진이 alert에 unknown을 쓰는지 확인한다 (지게차 노드는 unknown이면 멈춘다)."""

import json
import unittest

from engine.config import RiskConfig
from engine.main import RiskApplication
from engine.risk_engine import RiskEngine

# 이 시험의 거리 값은 11/19 이전 기준(3.0/1.5 m, CPA 1.0 m)으로 짜여 있다. 판단 로직 시험이므로 기준을 고정한다.
LEGACY = dict(warning_distance_m=3.0, danger_distance_m=1.5, cpa_radius_m=1.0)


class Writer:
    def __init__(self):
        self.calls = []

    def create_event_cin(self, body):
        self.calls.append(body)
        return {}


def radar(ri, targets):
    return {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {
        "ri": ri, "con": json.dumps({"ts": 1, "targets": targets})}}}}}


class AlertUnknownTest(unittest.TestCase):
    def test_stale_radar_writes_unknown_alert_and_fresh_radar_clears_it(self):
        now = [10.0]
        events, alerts = Writer(), Writer()
        engine = RiskEngine(RiskConfig(release_hold_s=0, **LEGACY), clock=lambda: now[0])
        app = RiskApplication(None, engine, events, alerts, wall_clock=lambda: 1)

        app.accept_message(radar("a", [{"slot": 0, "x": 1000, "y": 0}]), now[0], dedupe=True)
        self.assertEqual(alerts.calls[-1]["level"], "danger")
        now[0] = 10.5 + engine.config.stale_after_s          # 레이더 CIN이 더 오지 않음
        self.assertEqual(app.tick()["status"], "UNKNOWN")
        self.assertEqual(alerts.calls[-1], {"level": "unknown", "dist": None, "ttc": None})
        app.tick()
        self.assertEqual(len(alerts.calls), 2)                 # 같은 상태는 다시 쓰지 않는다
        # 레이더가 돌아와도 직전 표적이 사라진 직후 잠깐은 UNKNOWN을 유지한 뒤 SAFE가 된다
        for ri in "bcdef":
            now[0] += 0.5
            app.accept_message(radar(ri, []), now[0], dedupe=True)
        self.assertEqual(alerts.calls[-1]["level"], "safe")
        self.assertEqual([c["level"] for c in alerts.calls], ["danger", "unknown", "safe"])


if __name__ == "__main__":
    unittest.main()
