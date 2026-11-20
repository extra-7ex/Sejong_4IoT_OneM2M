import json
import time
import unittest

from engine.config import RiskConfig
from engine.main import RiskApplication
from engine.risk_engine import RiskEngine
from engine.vision_advice import ReleaseHold, apply_radar_advice, assess


class VisionAdviceTests(unittest.TestCase):
    def cin(self, payload, ri="vision-1"):
        return {"m2m:cin": {"ri": ri, "con": json.dumps(payload)}}

    def test_fresh_camera_only_raise_elevates_safe_to_warning(self):
        observation = assess(self.cin({
            "ts": 100.0,
            "cam_ok": True,
            "radar_ok": True,
            "tracks": [{"state": "camera_only", "advice": "raise"}],
        }), received_mono_s=1.0, received_unix_s=101.0)
        decision = apply_radar_advice({"status": "SAFE", "level": "safe"}, observation)
        self.assertEqual(decision["status"], "WARNING")
        self.assertEqual(decision["reason"], "vision_camera_only_raise")

    def test_stale_or_camera_fault_does_not_change_radar_safe(self):
        for payload, now in (
            ({"ts": 90.0, "cam_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}, 100.0),
            ({"ts": 100.0, "cam_ok": False, "tracks": [{"state": "camera_only", "advice": "raise"}]}, 100.0),
        ):
            observation = assess(self.cin(payload), received_mono_s=1.0, received_unix_s=now)
            decision = apply_radar_advice({"status": "SAFE", "level": "safe"}, observation)
            self.assertEqual(decision["status"], "SAFE")

    def test_vision_does_not_lower_existing_radar_warning_or_danger(self):
        observation = {"status": "fresh", "raise_warning": False}
        for status in ("WARNING", "DANGER"):
            decision = apply_radar_advice({"status": status}, observation)
            self.assertEqual(decision["status"], status)

    def test_radar_availability_requires_boolean_true(self):
        for value in (False, None, "true", 1):
            payload = {"ts": 100.0, "cam_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}
            if value is not None:
                payload["radar_ok"] = value
            observation = assess(self.cin(payload), 1.0, 100.5)
            self.assertEqual(observation["status"], "vision_radar_unavailable")
            self.assertEqual(apply_radar_advice({"status": "SAFE"}, observation)["status"], "SAFE")


def target(slot, distance, status, **extra):
    return {"target": str(slot), "distance_m": distance, "status": status,
            "association_valid": True, "held_previous_risk": False, **extra}


def radar(status, *targets):
    return {"status": status, "level": status.lower(), "reason": "radar", "targets": list(targets)}


def fresh(*tracks, age=0.2):
    return {"status": "fresh", "age_s": age, "raise_warning": False, "tracks": list(tracks)}


class FusionRuleTests(unittest.TestCase):
    def test_ghost_lower_is_disabled_by_default(self):
        decision = apply_radar_advice(radar("DANGER", target(0, 1.3, "DANGER")),
            fresh({"state": "ghost_suspect", "advice": "lower_to_caution", "radar_id": 0, "dist_m": 1.3}))
        self.assertEqual(decision["status"], "DANGER")

    def test_confirmed_risky_posture_raises_warning_target_to_danger(self):
        for posture in ("lying", "crouching"):
            decision = apply_radar_advice(
                radar("WARNING", target(0, 2.0, "WARNING")),
                fresh({"state": "confirmed", "advice": "raise", "radar_id": 0, "dist_m": 2.1, "posture": posture}))
            self.assertEqual(decision["status"], "DANGER")
            self.assertEqual(decision["level"], "danger")
            self.assertEqual(decision["reason"], "vision_risky_posture_raise")
            self.assertEqual(decision["radar_status"], "WARNING")

    def test_posture_raise_needs_same_slot_close_distance_and_risky_posture(self):
        for track in (
            {"state": "confirmed", "advice": "raise", "radar_id": 1, "dist_m": 2.0, "posture": "lying"},
            {"state": "confirmed", "advice": "raise", "radar_id": 0, "dist_m": 2.8, "posture": "lying"},
            {"state": "confirmed", "advice": "none", "radar_id": 0, "dist_m": 2.0, "posture": "standing"},
            {"state": "confirmed", "advice": "raise", "dist_m": 2.0, "posture": "lying"},
        ):
            decision = apply_radar_advice(radar("WARNING", target(0, 2.0, "WARNING")), fresh(track))
            self.assertEqual(decision["status"], "WARNING", track)

    def test_ghost_lowers_danger_to_warning_only(self):
        decision = apply_radar_advice(
            radar("DANGER", target(0, 1.3, "DANGER")),
            fresh({"state": "ghost_suspect", "advice": "lower_to_caution", "radar_id": 0, "dist_m": 1.35}), ghost_lower_enabled=True)
        self.assertEqual(decision["status"], "WARNING")
        self.assertEqual(decision["reason"], "vision_ghost_suspect_lowered")
        self.assertEqual(decision["vision_adjustments"][0]["rule"], "ghost_lower")

    def test_ghost_does_not_lower_when_close_old_mismatched_or_held(self):
        ghost = {"state": "ghost_suspect", "advice": "lower_to_caution", "radar_id": 0, "dist_m": 1.3}
        cases = (
            (radar("DANGER", target(0, 0.9, "DANGER")), fresh({**ghost, "dist_m": 0.9})),   # inside 1 m
            (radar("DANGER", target(0, 1.3, "DANGER")), fresh(ghost, age=1.5)),              # older than 1 s
            (radar("DANGER", target(0, 1.3, "DANGER")), fresh({**ghost, "radar_id": 2})),    # other slot
            (radar("DANGER", target(0, 1.3, "DANGER")), fresh({**ghost, "dist_m": 2.0})),    # other place
            (radar("DANGER", target(0, 1.3, "DANGER", held_previous_risk=True)), fresh(ghost)),
            (radar("DANGER", target(0, 1.3, "DANGER", association_valid=False)), fresh(ghost)),
        )
        for decision, observation in cases:
            self.assertEqual(apply_radar_advice(decision, observation, ghost_lower_enabled=True)["status"], "DANGER")

    def test_ghost_lower_keeps_other_real_danger(self):
        decision = apply_radar_advice(
            radar("DANGER", target(0, 1.3, "DANGER"), target(1, 1.2, "DANGER")),
            fresh({"state": "ghost_suspect", "advice": "lower_to_caution", "radar_id": 0, "dist_m": 1.3}), ghost_lower_enabled=True)
        self.assertEqual(decision["status"], "DANGER")
        self.assertEqual([t["status"] for t in decision["targets"]], ["WARNING", "DANGER"])

    def test_unknown_radar_is_never_changed_by_vision(self):
        observation = fresh({"state": "camera_only", "advice": "raise", "dist_m": 2.0})
        observation["raise_warning"] = True
        self.assertEqual(apply_radar_advice(radar("UNKNOWN"), observation)["status"], "UNKNOWN")


class ReleaseHoldTests(unittest.TestCase):
    def test_release_hold_can_be_set_to_one_and_half_seconds(self):
        hold = ReleaseHold(1.5)
        hold.apply({"status": "DANGER"}, 0.0)
        self.assertEqual(hold.apply({"status": "SAFE"}, 1.0)["status"], "DANGER")
        self.assertEqual(hold.apply({"status": "SAFE"}, 2.4)["status"], "DANGER")
        self.assertEqual(hold.apply({"status": "SAFE"}, 2.5)["status"], "SAFE")

    def test_safe_must_last_three_seconds(self):
        hold = ReleaseHold(3.0)
        self.assertEqual(hold.apply({"status": "DANGER"}, 0.0)["status"], "DANGER")
        held = hold.apply({"status": "SAFE", "reason": "fresh_frame_has_no_targets"}, 1.0)
        self.assertEqual((held["status"], held["level"], held["reason"]),
                         ("DANGER", "danger", "release_hold_waiting_for_safe"))
        self.assertEqual(hold.apply({"status": "SAFE"}, 3.9)["status"], "DANGER")
        self.assertEqual(hold.apply({"status": "SAFE"}, 4.0)["status"], "SAFE")
        self.assertEqual(hold.apply({"status": "SAFE"}, 4.5)["status"], "SAFE")

    def test_new_risk_restarts_the_safe_streak(self):
        hold = ReleaseHold(3.0)
        hold.apply({"status": "WARNING"}, 0.0)
        hold.apply({"status": "SAFE"}, 1.0)
        hold.apply({"status": "WARNING"}, 2.0)
        self.assertEqual(hold.apply({"status": "SAFE"}, 4.5)["status"], "WARNING")
        self.assertEqual(hold.apply({"status": "SAFE"}, 7.5)["status"], "SAFE")

    def test_downgrade_and_unknown_pass_immediately(self):
        hold = ReleaseHold(3.0)
        hold.apply({"status": "DANGER"}, 0.0)
        self.assertEqual(hold.apply({"status": "WARNING"}, 0.1)["status"], "WARNING")
        self.assertEqual(hold.apply({"status": "UNKNOWN"}, 0.2)["status"], "UNKNOWN")
        hold.apply({"status": "SAFE"}, 1.0)
        hold.apply({"status": "UNKNOWN"}, 2.0)  # breaks the SAFE streak
        self.assertEqual(hold.apply({"status": "SAFE"}, 4.5)["status"], "WARNING")
        self.assertEqual(hold.apply({"status": "SAFE"}, 7.5)["status"], "SAFE")


class FakeVisionCSE:
    def __init__(self):
        self.events, self.vision = [], None

    def create_event_cin(self, event):
        self.events.append(event["status"])
        return {}

    def get_latest_cin(self, path):
        return {"m2m:cin": {"ri": "v", "con": json.dumps({**self.vision, "ts": time.time()})}}, None


class ApplicationFusionTests(unittest.TestCase):
    def setUp(self):
        self.now = [10.0]
        self.cse = FakeVisionCSE()
        self.app = RiskApplication(self.cse, RiskEngine(RiskConfig(), clock=lambda: self.now[0]),
                                   vision_path="/AE-VisionAI/fusedTracks/la", wall_clock=lambda: 1)

    def frame(self, ri, targets):
        return {"m2m:cin": {"ri": ri, "con": json.dumps({"ts": 1, "targets": targets})}}

    def test_tick_keeps_vision_raise_and_release_waits_three_seconds(self):
        far = [{"slot": 0, "x": 0, "y": 5000}]
        self.cse.vision = {"cam_ok": True, "radar_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}
        self.assertEqual(self.app.accept_message(self.frame("a", far), self.now[0])["status"], "WARNING")
        self.now[0] = 10.2
        self.assertEqual(self.app.tick()["status"], "WARNING")  # a tick used to reset this to radar SAFE
        self.cse.vision = {"cam_ok": True, "radar_ok": True, "tracks": []}
        # Radar SAFE from 10.5 s; frames every 0.5 s keep the radar association valid.
        for step, expected in enumerate(["WARNING"] * 6 + ["SAFE"]):
            self.now[0] = 10.5 + 0.5 * step
            decision = self.app.accept_message(self.frame(f"f{step}", far), self.now[0])
            self.assertEqual(decision["status"], expected, self.now[0])
        self.assertEqual(self.cse.events, ["WARNING", "SAFE"])

    def test_radar_staleness_overrides_vision_warning(self):
        self.cse.vision = {"cam_ok": True, "radar_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}
        self.assertEqual(self.app.accept_message(self.frame("a", [{"slot": 0, "x": 0, "y": 5000}]), self.now[0])["status"], "WARNING")
        self.now[0] += 1.1
        self.assertEqual(self.app.tick()["status"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
