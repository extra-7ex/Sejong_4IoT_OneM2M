import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import mec_adapter_daemon as daemon

class AdapterTests(unittest.TestCase):
    def test_discovery_reads_only_valid_requests_from_configured_container(self):
        body = json.dumps({"m2m:uril": ["TinyIoT-MN/AE-test/requests/req-a1", "http://evil/req-b", "/TinyIoT-MN/other/requests/req-c"]}).encode()
        request = {"request_id": "a1", "operation": "get_latest_vision"}
        with patch.object(daemon.demo, "exchange", return_value=(200, "2000", body)) as exchange, patch.object(daemon.demo, "read_cin", return_value=request) as read:
            self.assertEqual(list(daemon.scan("http://localhost/TinyIoT-MN/AE-test/requests")), ["a1"])
            exchange.assert_called_once_with("http://localhost/TinyIoT-MN/AE-test/requests?fu=1&ty=4&drt=1&lim=21")
            read.assert_called_once_with("http://localhost/TinyIoT-MN/AE-test/requests/req-a1")

    def test_discovery_rejects_truncated_or_malformed_response(self):
        for body in ({"m2m:uril": ["x"] * 21}, {"m2m:uril": "not-a-list"}):
            with self.subTest(body=body), patch.object(daemon.demo, "exchange", return_value=(200, "2000", json.dumps(body).encode())):
                with self.assertRaises(ValueError):
                    list(daemon.scan("http://localhost/TinyIoT-MN/AE-test/requests"))

    def test_request_validation(self):
        cin = {"rn": "req-a1", "con": json.dumps({"request_id": "a1", "operation": "get_latest_vision"})}
        self.assertEqual(daemon.parse_request(cin), "a1")
        cin["con"] = "{}"
        with self.assertRaises(ValueError):
            daemon.parse_request(cin)

    def test_existing_result_avoids_duplicate_call(self):
        request = {"request_id": "a1", "operation": "get_latest_vision"}
        with patch.object(daemon.demo, "read_cin", side_effect=[request, {"call_status": "ok"}]), patch.object(daemon.demo, "result_for") as call:
            self.assertEqual(daemon.process("/ae", "a1")["call_status"], "ok")
            call.assert_not_called()

    def test_conflict_reads_result(self):
        request = {"request_id": "a1", "operation": "get_latest_vision"}
        missing = HTTPError("/res", 404, "missing", {}, None)
        conflict = HTTPError("/res", 409, "exists", {}, None)
        with patch.object(daemon.demo, "read_cin", side_effect=[request, missing, {"call_status": "ok"}]), patch.object(daemon.demo, "result_for", return_value={"call_status": "ok"}), patch.object(daemon.demo, "create", side_effect=conflict):
            self.assertEqual(daemon.process("/ae", "a1")["call_status"], "ok")

if __name__ == "__main__":
    unittest.main()
