"""Timestamp guards cover delayed MQTT replay and polling of old CINs."""
import unittest

from engine.config import RiskConfig
from engine.main import RiskApplication
from engine.risk_engine import RiskEngine


class Writer:
    def __init__(self):
        self.items = []

    def create_event_cin(self, item):
        self.items.append(item)
        return {}


def frame(ri, ts, targets):
    con = {"targets": targets}
    if ts is not None:
        con["ts"] = ts
    return {"m2m:cin": {"ri": ri, "con": con}}


class RadarFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.wall = [1000.0]
        self.mono = [10.0]
        self.events, self.alerts = Writer(), Writer()
        cfg = RiskConfig(radar_max_age_s=3, radar_future_skew_s=1,
                         target_loss_grace_s=0, release_hold_s=0)
        self.app = RiskApplication(None, RiskEngine(cfg, clock=lambda: self.mono[0]),
                                   self.events, self.alerts, wall_clock=lambda: self.wall[0])

    def accept(self, ri, ts, targets):
        return self.app.accept_message(frame(ri, ts, targets), self.mono[0], dedupe=True)

    def test_old_empty_frame_cannot_clear_danger_and_fresh_frame_recovers(self):
        self.assertEqual(self.accept('a', 1000, [{'x': 0, 'y': 400}])['status'], 'DANGER')
        result = self.accept('b', 990, [])
        self.assertEqual((result['status'], result['reason']), ('UNKNOWN', 'radar_timestamp_stale'))
        self.assertEqual(self.alerts.items[-1]['level'], 'unknown')
        self.mono[0] += 1
        self.assertEqual(self.accept('c', 1000, [])['status'], 'SAFE')

    def test_stale_duplicate_is_not_kept_safe(self):
        self.assertEqual(self.accept('a', 1000, [])['status'], 'SAFE')
        self.wall[0] += 4
        self.assertEqual(self.accept('a', 1000, [])['reason'], 'radar_timestamp_stale')

    def test_missing_future_and_boolean_timestamp_are_unknown(self):
        for ts, reason in [(None, 'radar_timestamp_missing'), (1002, 'radar_timestamp_future')]:
            with self.subTest(ts=ts):
                result = self.accept(str(ts), ts, [])
                self.assertEqual((result['status'], result['reason']), ('UNKNOWN', reason))
        self.assertEqual(self.accept('bool', True, [])['status'], 'UNKNOWN')

    def test_within_clock_tolerance_and_age_boundary(self):
        self.assertEqual(self.accept('future', 1001, [])['status'], 'SAFE')
        self.assertEqual(self.accept('old', 997, [])['status'], 'SAFE')


if __name__ == '__main__':
    unittest.main()
