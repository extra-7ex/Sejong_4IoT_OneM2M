import json
import unittest
from types import SimpleNamespace
from engine.mqtt_events import MQTTEventWriter, UncertainWriteError
from engine.main import RiskApplication
from engine.risk_engine import RiskEngine
from engine.config import RiskConfig


class MQTTEventTests(unittest.TestCase):
    def setUp(self):
        self.writer = MQTTEventWriter("localhost", 1883, "test-cse", "http://localhost:3000/TestCSE",
                                      "Criskengine", "/AE-riskengine/events", timeout=0.01)
        self.writer.ready.set()
        self.published = []
        writer, published = self.writer, self.published
        class FakeClient:
            code = 2001
            def publish(self, topic, payload, qos):
                request = json.loads(payload)
                published.append((topic, request, qos))
                if self.code is not None:
                    writer.on_message(None, None, SimpleNamespace(payload=json.dumps(
                        {"rqi": request["rqi"], "rsc": self.code}).encode()))
                return SimpleNamespace(rc=0)
        self.writer.client = FakeClient()

    def test_create_correlates_response_and_encodes_cin(self):
        result = self.writer.create_event_cin({"status": "WARNING"})
        topic, req, qos = self.published[0]
        self.assertEqual((topic, qos), ("/oneM2M/req/Criskengine/test-cse/json", 1))
        self.assertEqual(req["to"], "TestCSE/AE-riskengine/events")
        self.assertEqual(json.loads(req["pc"]["m2m:cin"]["con"])["status"], "WARNING")
        self.assertEqual(result["rqi"], req["rqi"])
        self.assertEqual(result["rsc"], 2001)

    def test_rejection_is_not_success(self):
        self.writer.client.code = 4103
        with self.assertRaises(RuntimeError):
            self.writer.create_event_cin({"status": "UNKNOWN"})

    def test_publish_without_onem2m_response_is_not_success(self):
        self.writer.client.code = None
        with self.assertRaises(UncertainWriteError):
            self.writer.create_event_cin({"status": "UNKNOWN"})
        self.assertEqual(self.writer.pending, {})

    def test_uncertain_write_does_not_retry_same_status_automatically(self):
        self.writer.client.code = None
        app = RiskApplication(None, RiskEngine(RiskConfig()), self.writer)
        decision = {"status": "WARNING", "reason": "test"}
        with self.assertLogs("safezone-riskengine", level="ERROR"):
            app.publish_transition(decision)
        app.publish_transition(decision)
        self.assertEqual(len(self.published), 1)
        self.assertIsNone(app.last_published_status)
        self.assertEqual(app.uncertain_event_status, "WARNING")


if __name__ == "__main__":
    unittest.main()
