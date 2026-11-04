import unittest

from engine.config import RiskConfig
from engine.risk_engine import InputError, RiskEngine, normalize_radar_cin


def cin(ri, ts, targets):
    return {"m2m:cin": {"ri": ri, "con": {"ts": ts, "targets": targets}}}


class NormalizationTests(unittest.TestCase):
    def test_readme_shape_and_units_preserved(self):
        frame = normalize_radar_cin(cin("cin-1", 1760360000.12, [{"x": 373, "y": 366, "v": -8}]))
        self.assertEqual(frame.sensor_ts_unix_s, 1760360000.12)
        self.assertEqual(frame.targets[0].x_mm, 373)
        self.assertEqual(frame.targets[0].speed_cm_s_raw, -8)
        self.assertEqual(frame.targets[0].key, "1")

    def test_notification_envelope_and_string_con(self):
        msg = {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {
            "ri": "cin-n1", "con": '{"ts":10.0,"targets":[{"slot":2,"x":1000,"y":0}]}'
        }}}}}
        frame = normalize_radar_cin(msg)
        self.assertEqual(frame.cin_ri, "cin-n1")
        self.assertEqual(frame.targets[0].key, "2")

    def test_bad_or_missing_targets_rejected(self):
        with self.assertRaises(InputError):
            normalize_radar_cin({"m2m:cin": {"con": {"ts": 1}}})
        with self.assertRaises(InputError):
            normalize_radar_cin(cin("bad", 1, [{"x": "nan", "y": 0}]))


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.engine = RiskEngine(RiskConfig())

    def test_distance_levels_and_boundary_priority(self):
        def classify(x_mm):
            return RiskEngine(RiskConfig()).process_message(
                cin("threshold", 1, [{"x": x_mm, "y": 0}]), 1
            )["status"]
        self.assertEqual(classify(3000), "WARNING")
        self.assertEqual(classify(1500), "DANGER")
        self.assertEqual(classify(3001), "SAFE")

    def test_cpa_is_closest_approach_time_and_distance(self):
        self.engine.process_message(cin("a", 100, [{"x": 3000, "y": 0}]), 10.0)
        result = self.engine.process_message(cin("b", 1, [{"x": 2000, "y": 0}]), 10.5)
        self.assertEqual(result["status"], "DANGER")
        self.assertAlmostEqual(result["t_cpa_s"], 1.0)
        self.assertAlmostEqual(result["d_cpa_m"], 0.0)
        self.assertEqual(result["sample_interval_s"], 0.5)
        self.assertEqual(result["sensor_ts_unix_s"], 1.0)  # sensor clock jump is metadata only

    def test_side_pass_outside_cpa_radius_is_not_cpa_warning(self):
        self.engine.process_message(cin("a", 1, [{"x": 1500, "y": 4000}]), 1.0)
        result = self.engine.process_message(cin("b", 2, [{"x": 1500, "y": 3000}]), 1.5)
        self.assertEqual(result["status"], "SAFE")
        self.assertAlmostEqual(result["d_cpa_m"], 1.5)

    def test_new_track_has_distance_decision_but_no_cpa(self):
        result = self.engine.process_message(cin("a", 1, [{"slot": 3, "x": 2000, "y": 0}]), 1)
        self.assertEqual(result["status"], "WARNING")
        self.assertIsNone(result["t_cpa_s"])

    def test_implausible_same_slot_jump_is_unknown_not_safe(self):
        self.engine.process_message(cin("a", 1, [{"slot": 1, "x": 5000, "y": 0}]), 1.0)
        result = self.engine.process_message(cin("b", 2, [{"slot": 1, "x": 9000, "y": 0}]), 1.1)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["reason"], "target_association_uncertain")

    def test_slot_change_holds_previous_risk_during_track_loss_grace(self):
        self.engine.process_message(cin("a", 1, [{"slot": 1, "x": 1200, "y": 0}]), 1.0)
        result = self.engine.process_message(cin("b", 2, [{"slot": 2, "x": 5000, "y": 0}]), 1.2)
        self.assertEqual(result["status"], "DANGER")
        self.assertEqual(result["reason"], "track_missing_hold_previous_risk")
        still_missing = self.engine.process_message(cin("c", 3, [{"slot": 2, "x": 5000, "y": 0}]), 1.5)
        self.assertEqual(still_missing["status"], "DANGER")
        after_grace = self.engine.process_message(cin("d", 4, [{"slot": 2, "x": 5000, "y": 0}]), 2.21)
        self.assertEqual(after_grace["status"], "SAFE")

    def test_track_loss_does_not_switch_immediately_to_safe(self):
        self.engine.process_message(cin("a", 1, [{"x": 1200, "y": 0}]), 1.0)
        interim = self.engine.process_message(cin("b", 2, []), 1.2)
        self.assertEqual(interim["status"], "DANGER")  # retain last risk during short loss
        self.assertTrue(interim["held_previous_risk"])
        settled = self.engine.process_message(cin("c", 3, []), 2.21)
        self.assertEqual(settled["status"], "SAFE")

    def test_stale_and_malformed_input_are_unknown(self):
        self.engine.process_message(cin("a", 1, [{"x": 5000, "y": 0}]), 1.0)
        self.assertEqual(self.engine.snapshot(2.01)["status"], "UNKNOWN")
        self.assertEqual(self.engine.process_message({"m2m:cin": {"con": "oops"}}, 2.1)["status"], "UNKNOWN")

    def test_zero_or_too_long_dt_disables_cpa(self):
        self.engine.process_message(cin("a", 1, [{"x": 3000, "y": 0}]), 1.0)
        result = self.engine.process_message(cin("b", 2, [{"x": 2000, "y": 0}]), 2.0)
        self.assertEqual(result["status"], "WARNING")
        self.assertFalse(result["cpa_valid"])


if __name__ == "__main__":
    unittest.main()
