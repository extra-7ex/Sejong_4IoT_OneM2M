"""python3 -m unittest onem2m.test_mn_to_in_bridge"""

import json
import tempfile
import unittest
from pathlib import Path

from onem2m.mn_to_in_bridge import MAX_CON_BYTES, Bridge, load_config, summarize


class FakeCse:
    def __init__(self):
        self.store = {}      # path -> list of con (CIN) or {} (AE/CNT)
        self.posts = []

    def request(self, method, path="", ty=None, body=None):
        if method == "GET":
            if path.endswith("/la"):
                items = self.store.get(path[:-3])
                if not items:
                    return 404, None
                ri, con = items[-1]
                return 200, {"m2m:cin": {"ri": ri, "con": con}}
            return (200, {}) if path in self.store else (404, None)
        self.posts.append((path, ty, body))
        if ty == 2:
            self.store["/" + body["m2m:ae"]["rn"]] = []
        elif ty == 3:
            self.store[f"{path}/{body['m2m:cnt']['rn']}"] = []
        elif ty == 4:
            if path not in self.store:
                return 404, None
            self.store[path].append((f"in-{len(self.store[path])}", body["m2m:cin"]["con"]))
        return 201, {}


BIG_EVENT = {
    "schema": "safezone.risk-event.v1", "status": "DANGER", "reason": "cpa_inside_radius_" + "x" * 80,
    "distance_m": 1.23456, "t_cpa_s": 0.876, "d_cpa_m": 0.2, "target_count": 3,
    "sensor_ts_unix_s": 1794908041.36, "assumptions": ["a" * 300], "targets": [{"x": 1}] * 20,
}
RADAR = {"ri": "r1", "con": {"ts": 1, "targets": [{"slot": i, "x": 1000 + i, "y": -2000 - i, "v": 10} for i in range(3)]}}


class BridgeTest(unittest.TestCase):
    def test_summary_fits_and_keeps_core_fields(self):
        text = summarize(BIG_EVENT, "4-20261117T093036,7080461", RADAR)
        self.assertLessEqual(len(text.encode()), MAX_CON_BYTES)
        con = json.loads(text)
        self.assertEqual(con["status"], "DANGER")
        self.assertEqual(con["distance_m"], 1.23)
        self.assertIn("ts", con)

    def test_summary_unknown_event_shape(self):
        con = json.loads(summarize("not a dict", None, None))
        self.assertEqual(con["status"], "UNKNOWN")

    def test_forward_once_per_event_and_create_resources(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config()
            cfg["state_file"] = str(Path(tmp) / "state.json")
            br = Bridge(cfg)
            br.mn, br.inn = FakeCse(), FakeCse()
            br.mn.store["/AE-riskengine/events"] = [("mn-1", json.dumps(BIG_EVENT))]
            br.mn.store["/AE-forklift01/radar"] = [("r1", json.dumps(RADAR["con"]))]
            self.assertTrue(br.step())
            self.assertFalse(br.step())                      # 같은 이벤트는 한 번만
            self.assertEqual(len(br.inn.store["/AE-safezone/events"]), 1)
            br.mn.store["/AE-riskengine/events"].append(("mn-2", json.dumps({**BIG_EVENT, "status": "SAFE"})))
            self.assertTrue(br.step())
            self.assertEqual(len(br.inn.store["/AE-safezone/events"]), 2)
            again = Bridge(cfg)                              # 재시작해도 마지막 전달 위치를 기억
            again.mn, again.inn = br.mn, br.inn
            again.ready = True
            self.assertFalse(again.step())


if __name__ == "__main__":
    unittest.main()
