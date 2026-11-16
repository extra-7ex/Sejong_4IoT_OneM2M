import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import mec_adapter_daemon as daemon

class AdapterTests(unittest.TestCase):
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
