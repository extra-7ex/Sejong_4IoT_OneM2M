"""python -m unittest dashboard.test_dashboard"""

import json
import tempfile
import unittest
from pathlib import Path

from dashboard.server import Poller, Store, load_config, unwrap_cin


class FakeClient:
    def __init__(self):
        self.responses = {}
        self.history = []

    def latest(self, path, base=None):
        return self.responses.get(path, ("empty", None))

    def children(self, base, cnt_path):
        return [unwrap_cin({"m2m:cin": c}) for c in self.history]

    def health(self, base):
        return {"ok": True}


def event_cin(ri, status, distance):
    return {"ri": ri, "con": json.dumps({"status": status, "reason": "r", "distance_m": distance})}


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cfg = load_config()
        cfg["history_file"] = str(Path(self.tmp.name) / "events.jsonl")
        self.cfg = cfg
        self.store = Store(cfg)
        self.client = FakeClient()
        self.poller = Poller(cfg, self.store, self.client)

    def tearDown(self):
        self.tmp.cleanup()

    def set(self, key, cin):
        self.client.responses[self.cfg[key]] = ("ok", unwrap_cin({"m2m:cin": cin}))

    def test_con_string_and_object(self):
        self.assertEqual(unwrap_cin({"m2m:cin": {"ri": "a", "con": '{"x": 1}'}})["con"], {"x": 1})
        self.assertEqual(unwrap_cin({"m2m:cin": {"ri": "a", "con": {"x": 1}}})["con"], {"x": 1})
        self.assertIsNone(unwrap_cin({"m2m:cnt": {}}))

    def test_preexisting_event_not_recorded_then_new_ones_are(self):
        self.set("radar_path", {"ri": "r1", "con": {"ts": 1, "targets": [{"x": 300, "y": 1200, "v": -20}]}})
        self.set("events_path", event_cin("e1", "WARNING", 2.0))
        self.poller.poll_once()
        self.assertEqual(self.store.recent(10), [])           # 실행 전 이벤트는 이력에 넣지 않음
        self.poller.poll_once()
        self.assertEqual(self.store.recent(10), [])           # 같은 ri 중복 없음
        self.set("events_path", event_cin("e2", "DANGER", 1.2))
        self.poller.poll_once()
        rows = self.store.recent(10)
        self.assertEqual([r["ri"] for r in rows], ["e2"])
        self.assertEqual(rows[0]["radar_xy_mm"], [[300, 1200]])
        stats = self.store.stats(3600)
        self.assertEqual(stats["counts"]["DANGER"], 1)
        self.assertEqual(stats["hotspots"][0]["DANGER"], 1)

    def test_first_event_after_empty_container_is_recorded(self):
        self.poller.poll_once()                               # events CNT 비어 있음
        self.set("events_path", event_cin("e1", "SAFE", 4.0))
        self.poller.poll_once()
        self.assertEqual([r["ri"] for r in self.store.recent(10)], ["e1"])

    def test_history_reloaded_from_file(self):
        self.poller.poll_once()
        self.set("events_path", event_cin("e1", "DANGER", 1.0))
        self.poller.poll_once()
        again = Store(self.cfg)
        self.assertEqual([r["ri"] for r in again.recent(10)], ["e1"])


class InModeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cfg = load_config()
        cfg["history_file"] = str(Path(self.tmp.name) / "events.jsonl")
        cfg["in_base"] = "http://in.example/TinyIoT"
        self.cfg = cfg
        self.store = Store(cfg)
        self.client = FakeClient()
        self.poller = Poller(cfg, self.store, self.client)

    def tearDown(self):
        self.tmp.cleanup()

    def summary(self, ri, status, ts, xy=None):
        con = {"ts": ts, "status": status, "reason": "r", "distance_m": 1.2, "n": 1}
        if xy:
            con["xy_mm"] = xy
        return {"ri": ri, "con": con}

    def test_backfill_then_new_la_without_duplicates(self):
        import time
        now = time.time()
        self.client.history = [self.summary("a", "WARNING", now - 120), self.summary("b", "DANGER", now - 60, [[100, 900]])]
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": self.client.history[-1]}))
        self.poller.poll_once()
        self.assertTrue(self.store.history_loaded)
        self.assertEqual([r["ri"] for r in self.store.recent(10)], ["b", "a"])   # la("b")는 중복이라 제외
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": self.summary("c", "SAFE", now)}))
        self.poller.poll_once()
        self.assertEqual([r["ri"] for r in self.store.recent(10)], ["c", "b", "a"])
        stats = self.store.stats(3600)
        self.assertEqual(stats["counts"]["DANGER"], 1)
        self.assertEqual(stats["hotspots"][0]["DANGER"], 1)
        self.assertFalse(Path(self.cfg["history_file"]).exists())             # IN 모드는 로컬 파일을 쓰지 않음

    def test_duplicate_in_copies_of_same_mn_event_shown_once(self):
        a = self.summary("x1", "DANGER", 1.0); a["con"]["mn_ri"] = "mn-7"
        b = self.summary("x2", "DANGER", 1.0); b["con"]["mn_ri"] = "mn-7"
        self.client.history = [a, b]
        self.poller.poll_once()
        self.assertEqual([r["ri"] for r in self.store.recent(10)], ["x1"])

    def test_mn_events_not_recorded_locally_in_in_mode(self):
        self.poller.poll_once()
        self.set_mn_event()
        self.poller.poll_once()
        self.assertEqual(self.store.recent(10), [])

    def set_mn_event(self):
        self.client.responses[self.cfg["events_path"]] = ("ok", unwrap_cin({"m2m:cin": event_cin("e9", "DANGER", 1.0)}))


if __name__ == "__main__":
    unittest.main()
