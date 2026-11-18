import json
import unittest

from engine.vision_advice import apply_radar_advice, assess


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

    def test_vision_radar_must_be_explicitly_available(self):
        for radar_ok in (False, None, "true", 1):
            payload = {"ts": 100.0, "cam_ok": True, "tracks": [{"state": "camera_only", "advice": "raise"}]}
            if radar_ok is not None:
                payload["radar_ok"] = radar_ok
            observation = assess(self.cin(payload), received_mono_s=1.0, received_unix_s=100.5)
            self.assertEqual(observation["status"], "vision_radar_unavailable")
            self.assertEqual(apply_radar_advice({"status": "SAFE"}, observation)["status"], "SAFE")


if __name__ == "__main__":
    unittest.main()
