"""python3 -m unittest onem2m.test_alarm_group"""

import unittest

from onem2m import alarm_group as ag
from engine.onem2m_http import HTTPAlertWriter, check_fanout


class FakeMn:
    """라벨 검색(fu=1&ty&lbl)·PUT·그룹 생성만 흉내 내는 가짜 MN. 리소스는 경로 → (ty, 속성)."""

    def __init__(self):
        self.res = {
            "/AE-forklift01": (2, {"aei": "Cforklift01"}),
            "/AE-forklift01/radar": (3, {"ri": "3-radar"}),
            "/AE-forklift01/alert": (3, {"ri": "3-fk", "acpi": ["TinyIoT-MN/AE-forklift01/acp-alert"]}),
            "/AE-forklift01/acp-alert": (1, {"pv": {"acr": [{"acor": ["Cforklift01"], "acop": 63},
                                                             {"acor": ["Criskengine"], "acop": 3}]}}),
            "/AE-zonealarm01/alert": (3, {"ri": "3-zone", "pi": "Czonealarm01"}),
            "/AE-worker01": (2, {"aei": "Cworker01", "lbl": ["type:worker-alarm"]}),
            "/AE-worker01/alert": (3, {"ri": "3-wk", "acpi": ["TinyIoT-MN/AE-worker01/acp-worker01"]}),
            "/AE-worker01/acp-worker01": (1, {"pv": {"acr": [{"acor": ["Cworker01"], "acop": 63},
                                                              {"acor": ["Criskengine", "CAdmin"], "acop": 35}]}}),
        }
        self.calls = []

    def __call__(self, path, method="GET", body=None, ty=None, timeout=5):
        self.calls.append((method, path))
        if method == "GET" and path == "":
            return 200, {"m2m:cb": {}}
        if method == "GET" and path.startswith("?fu=1"):
            q = dict(p.split("=", 1) for p in path[1:].split("&"))
            hits = [p for p, (t, a) in self.res.items()
                    if ("ty" not in q or t == int(q["ty"])) and q.get("lbl") in (a.get("lbl") or [])]
            return 200, {"m2m:uril": ["TinyIoT-MN" + p for p in hits]}
        if method == "GET":
            if path not in self.res:
                return 404, None
            t, a = self.res[path]
            return 200, {ag.TY_KEY[t]: dict(a, ty=t)}
        if method == "PUT":
            t, a = self.res[path]
            a.update(next(iter(body.values())))
            return 200, {}
        if method == "DELETE":
            return (200, {}) if self.res.pop(path, None) else (404, None)
        if method == "POST" and ty == 1:
            self.res[f"{path}/{body['m2m:acp']['rn']}"] = (1, dict(body["m2m:acp"]))
            return 201, {}
        if method == "POST" and ty == 9:
            grp = dict(body["m2m:grp"], cnm=len(body["m2m:grp"]["mid"]), mtv=True)
            self.res["/" + grp["rn"]] = (9, grp)
            return 201, {"m2m:grp": grp}
        return 400, None


class AlarmGroupTest(unittest.TestCase):
    def setUp(self):
        self.mn = FakeMn()

    def test_labels_find_every_alarm_device_and_build_the_group(self):
        self.assertEqual(ag.main([], req=self.mn), 0)
        self.assertIn(ag.ALARM_LABEL, self.mn.res["/AE-forklift01/alert"][1]["lbl"])
        self.assertIn("unit:mm", self.mn.res["/AE-forklift01/radar"][1]["lbl"])
        grp = self.mn.res["/" + ag.GROUP_RN][1]
        self.assertEqual(grp["mt"], 3)
        self.assertEqual(sorted(grp["mid"]), ["TinyIoT-MN/AE-forklift01/alert", "TinyIoT-MN/AE-worker01/alert",
                                              "TinyIoT-MN/AE-zonealarm01/alert"])

    def test_writers_get_create_rights_on_the_worker_acp_only_when_missing(self):
        ag.main([], req=self.mn)
        worker = self.mn.res["/AE-worker01/acp-worker01"][1]["pv"]["acr"]
        self.assertIn({"acor": ["Cforklift01"], "acop": 3}, worker)          # Criskengine had 35 (create+retrieve)
        forklift = self.mn.res["/AE-forklift01/acp-alert"][1]["pv"]["acr"]
        self.assertEqual(len(forklift), 2)                                    # both writers already allowed
        zone = self.mn.res["/AE-zonealarm01/acp-alarm-writers"][1]["pv"]["acr"]  # no ACP before → made one
        self.assertEqual(zone, [{"acor": ["Czonealarm01"], "acop": 63}, {"acor": ag.WRITERS, "acop": 3}])
        self.assertEqual(self.mn.res["/AE-zonealarm01/alert"][1]["acpi"],
                         ["TinyIoT-MN/AE-zonealarm01/acp-alarm-writers"])

    def test_existing_labels_are_kept_and_a_rerun_changes_nothing(self):
        self.mn.res["/AE-forklift01/radar"][1]["lbl"] = ["team:4iot"]
        ag.main([], req=self.mn)
        self.assertEqual(self.mn.res["/AE-forklift01/radar"][1]["lbl"][0], "team:4iot")
        self.assertEqual(ag.apply_labels(self.mn, ag.LABELS), [])

    def test_show_changes_nothing(self):
        ag.main(["--show"], req=self.mn)
        self.assertTrue(all(m == "GET" for m, _ in self.mn.calls))


class FanoutResponseTest(unittest.TestCase):
    def agr(self, *rscs):
        return {"response": {"m2m:agr": {"m2m:rsp": [{"rsc": r, "to": f"m{i}"} for i, r in enumerate(rscs)]}}}

    def test_plain_container_response_passes(self):
        check_fanout({"response": {"m2m:cin": {}}})

    def test_one_member_failing_is_logged_not_raised(self):
        with self.assertLogs("engine.onem2m_http", "WARNING"):
            check_fanout(self.agr(2001, 4103))

    def test_no_member_reached_raises(self):
        with self.assertRaises(RuntimeError):
            check_fanout(self.agr(4103, 4004))
        with self.assertRaises(RuntimeError):
            check_fanout({"response": {"m2m:agr": {"m2m:rsp": []}}})

    def test_alert_writer_checks_the_group_response(self):
        class Http:
            def create_cin(_, path, event):
                return self.agr(4103)
        with self.assertRaises(RuntimeError):
            HTTPAlertWriter(Http(), "/grp-safezone-alarms/fopt").create_event_cin({"level": "danger"})


if __name__ == "__main__":
    unittest.main()
