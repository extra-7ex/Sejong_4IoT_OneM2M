"""python -m unittest dashboard.test_dashboard"""

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from dashboard.server import Poller, Store, cin_created_at, load_config, unwrap_cin


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
        cfg["fresh"] = False                                  # 기존 테스트는 전체 이력 기준
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

    def test_source_freshness_uses_sensor_timestamp_on_first_read(self):
        with patch("dashboard.server.time.time", return_value=100):
            self.set("radar_path", {"ri": "old", "con": {"ts": 10, "targets": []}})
            self.set("fused_path", {"ri": "now", "con": {"ts": 99, "tracks": []}})
            self.poller.poll_once()
            sources = self.store.snapshot()["sources"]
        self.assertEqual((sources["radar"]["freshness"], sources["radar"]["data_age_s"]), ("stale", 90))
        self.assertEqual((sources["fused"]["freshness"], sources["fused"]["data_age_s"]), ("fresh", 1))

    def test_future_missing_and_failed_source_are_not_fresh(self):
        with patch("dashboard.server.time.time", return_value=100):
            self.set("radar_path", {"ri": "future", "con": {"ts": 110, "targets": []}})
            self.set("fused_path", {"ri": "missing", "con": {"tracks": []}})
            self.poller.poll_once()
            sources = self.store.snapshot()["sources"]
            self.assertEqual(sources["radar"]["freshness"], "future")
            self.assertEqual(sources["fused"]["freshness"], "invalid_timestamp")
            self.client.responses[self.cfg["radar_path"]] = ("error:HTTP 403", None)
            self.poller.poll_once()
            self.assertEqual(self.store.snapshot()["sources"]["radar"]["freshness"], "unavailable")

    def test_event_age_uses_cin_creation_time_not_first_observation(self):
        with patch("dashboard.server.time.time", return_value=100):
            self.set("events_path", {"ri": "e", "ct": "19700101T000010,123", "con": {"status": "SAFE"}})
            self.poller.poll_once()
            event = self.store.snapshot()["sources"]["events"]
        self.assertEqual(event["age_s"], 0)
        self.assertEqual(event["created_age_s"], 90)
        self.assertIsNone(cin_created_at("invalid"))

    def test_configured_health_path_checks_allowed_resource(self):
        self.cfg["mn_health_path"] = "/AE-forklift01/radar/la"
        with patch.object(self.client, "health", return_value={"ok": True}) as health:
            self.poller.check_health()
        health.assert_called_once_with(self.cfg["cse_base"] + self.cfg["mn_health_path"])

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
        cfg["fresh"] = False                                  # 기존 테스트는 전체 이력 기준
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

    def test_in_mode_can_skip_backfill_and_read_latest(self):
        self.cfg["in_backfill"] = False
        store = Store(self.cfg)
        poller = Poller(self.cfg, store, self.client)
        latest = self.summary("latest", "WARNING", 100)
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": latest}))
        with patch.object(self.client, "children", side_effect=AssertionError("backfill was called")):
            poller.poll_once()
        self.assertEqual([r["ri"] for r in store.recent(10)], ["latest"])

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

    def test_vision_status_from_ipe_is_exposed(self):
        self.poller.poll_once()
        self.assertEqual(self.store.snapshot()["sources"]["vision_status"]["state"], "empty")
        self.client.responses[self.cfg["vision_status_path"]] = ("ok", unwrap_cin({"m2m:cin": {"ri": "s1", "con": json.dumps(
            {"service": "safezone-vision", "state": "INACTIVE", "reason": "stale 4.2s", "ts": 1, "since": 1})}}))
        self.poller.poll_once()
        src = self.store.snapshot()["sources"]["vision_status"]
        self.assertEqual((src["state"], src["con"]["state"]), ("ok", "INACTIVE"))

    def test_fresh_hides_old_in_history_and_shows_new(self):
        import time
        self.cfg["fresh"] = True
        store = Store(self.cfg)
        poller = Poller(self.cfg, store, self.client)
        old = self.summary("old", "DANGER", store.started - 60, [[100, 900]])
        self.client.history = [old]
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": old}))
        poller.poll_once()
        self.assertTrue(store.history_loaded)
        self.assertEqual(store.recent(10), [])                                  # 실행 전 이력은 숨김
        self.assertEqual(store.stats(3600)["counts"]["DANGER"], 0)
        new = self.summary("new", "WARNING", time.time() + 1)
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": new}))
        poller.poll_once()
        self.assertEqual([r["ri"] for r in store.recent(10)], ["new"])
        self.assertTrue(store.snapshot()["history"]["fresh"])


    def test_reset_clears_screen_and_keeps_new(self):
        import time
        self.client.history = [self.summary("a", "DANGER", time.time() - 60)]
        self.poller.poll_once()
        self.assertEqual(len(self.store.recent(10)), 1)
        self.store.reset()
        self.assertEqual(self.store.recent(10), [])
        self.assertEqual(self.store.stats(3600)["total"], 0)
        self.client.responses[self.cfg["in_events_path"] + "/la"] = ("ok", unwrap_cin({"m2m:cin": self.summary("b", "SAFE", time.time() + 1)}))
        self.poller.poll_once()
        self.assertEqual([r["ri"] for r in self.store.recent(10)], ["b"])

    def test_fresh_is_default(self):
        import os
        os.environ.pop("DASH_FRESH", None)
        self.assertTrue(load_config()["fresh"])


class FreshLocalTest(DashboardTest):
    def test_fresh_skips_file_but_keeps_it(self):
        self.poller.poll_once()
        self.set("events_path", event_cin("e1", "DANGER", 1.0))
        self.poller.poll_once()
        self.cfg["fresh"] = True
        again = Store(self.cfg)
        self.assertEqual(again.recent(10), [])                                  # 화면에서는 비움
        self.assertTrue(Path(self.cfg["history_file"]).read_text(encoding="utf-8").strip())  # 파일은 그대로


if __name__ == "__main__":
    unittest.main()
