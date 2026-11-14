import json
import time
import unittest
from types import SimpleNamespace

from engine.config import RiskConfig
from engine.main import RiskApplication
from engine.mqtt_notification import MQTTNotifications
from engine.risk_engine import RiskEngine


class FakeCSE:
    def __init__(self):
        self.events = []
    def create_event_cin(self, event):
        self.events.append(event)
        return {}


def packet(ri="id-1", x=2000):
    return {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {
        "ri": ri, "con": json.dumps({"ts": 1, "targets": [{"slot": 0, "x": x, "y": 0}]})
    }}}}}


class MQTTNotificationTests(unittest.TestCase):
    def setUp(self):
        self.cse = FakeCSE()
        self.app = RiskApplication(self.cse, RiskEngine(RiskConfig()))
        self.rx = MQTTNotifications(self.app, "127.0.0.1", 1883, "/oneM2M/req/test/engine/json")

    def deliver(self, payload, retain=False):
        self.rx.on_message(None, None, SimpleNamespace(payload=payload, retain=retain))
        self.rx.process_next(timeout=0)

    def test_verification_does_not_create_radar_frame(self):
        self.deliver(b'{"m2m:sgn":{"vrq":true}}')
        self.assertEqual(self.cse.events, [])

    def test_real_envelope_classifies_and_duplicate_does_not_repeat_event(self):
        payload = json.dumps(packet()).encode()
        self.deliver(payload)
        self.assertEqual(self.cse.events[-1]["status"], "WARNING")
        self.deliver(payload)
        self.assertEqual(len(self.cse.events), 1)

    def test_disconnect_stays_unknown_even_on_tick(self):
        self.deliver(json.dumps(packet()).encode())
        self.rx.on_disconnect(None, None, None, None, None)
        self.rx.process_next(timeout=0)
        self.assertEqual(self.app.tick()["status"], "UNKNOWN")
        self.assertEqual(self.cse.events[-1]["reason"], "mqtt_disconnected")

    def test_retain_and_invalid_payload_are_unknown(self):
        self.deliver(json.dumps(packet()).encode(), retain=True)
        self.assertEqual(self.cse.events[-1]["status"], "UNKNOWN")
        self.deliver(b"not json")
        self.assertIn("mqtt_invalid_notification", self.app.engine.input_fault)

    def test_old_queued_message_is_rejected(self):
        self.rx._put(("message", json.dumps(packet()).encode(), time.monotonic() - 4))
        self.rx.process_next(timeout=0)
        self.assertEqual(self.app.engine.input_fault, "mqtt_notification_queue_stale")

    def test_queue_overflow_fails_unknown(self):
        self.rx = MQTTNotifications(self.app, "127.0.0.1", 1883, "/topic", queue_size=1)
        self.deliver(json.dumps(packet()).encode())
        self.rx._put(("message", b"{}", time.monotonic()))
        self.rx._put(("message", b"{}", time.monotonic()))
        self.rx.process_next(timeout=0)
        self.assertEqual(self.app.engine.input_fault, "mqtt_notification_queue_overflow")
        self.assertTrue(self.rx.queue.empty())


if __name__ == "__main__":
    unittest.main()
