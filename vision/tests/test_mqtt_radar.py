import json
import unittest
from types import SimpleNamespace

from vision4iot.radar.mqtt_in import MQTTRadar


class MQTTRadarTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.radar = MQTTRadar("localhost", 1883, "/test", clock=lambda: self.now)

    def send(self, ri, targets, retain=False):
        cin = {"ri": ri, "con": json.dumps({"ts": 1, "targets": targets})}
        body = {"m2m:sgn": {"nev": {"rep": {"m2m:cin": cin}}}}
        self.radar.on_message(None, None, SimpleNamespace(
            payload=json.dumps(body).encode(), retain=retain))

    def test_empty_frame_is_valid_and_duplicate_does_not_refresh(self):
        self.send("a", [])
        self.assertEqual(self.radar.get(), ([], True))
        self.now += 2
        self.send("a", [])
        self.assertEqual(self.radar.get(), ([], False))
        self.send("b", [])
        self.assertEqual(self.radar.get(), ([], True))

    def test_target_and_disconnect(self):
        self.send("a", [{"slot": 0, "x": 1000, "y": 2000, "v": 0}])
        targets, ok = self.radar.get()
        self.assertTrue(ok)
        self.assertAlmostEqual(targets[0].x, 1.0)
        self.radar.on_disconnect(None, None, None, None, None)
        self.assertEqual(self.radar.get(), ([], False))

    def test_retain_and_invalid_clear_existing_frame(self):
        self.send("a", [])
        self.send("b", [], retain=True)
        self.assertEqual(self.radar.get(), ([], False))
        self.send("c", [])
        self.radar.on_message(None, None, SimpleNamespace(payload=b"bad", retain=False))
        self.assertEqual(self.radar.get(), ([], False))

    def test_missing_targets_is_not_an_empty_frame(self):
        self.send("a", [])
        body = {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {
            "ri": "b", "con": "{}"
        }}}}}
        self.radar.on_message(None, None, SimpleNamespace(
            payload=json.dumps(body).encode(), retain=False))
        self.assertEqual(self.radar.get(), ([], False))

    def test_verification_does_not_refresh_input(self):
        self.radar.on_message(None, None, SimpleNamespace(
            payload=b'{"m2m:sgn":{"vrq":true}}', retain=False))
        self.assertEqual(self.radar.get(), ([], False))


if __name__ == "__main__":
    unittest.main()
