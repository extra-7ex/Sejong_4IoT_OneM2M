"""python3 -m unittest onem2m.test_mec_ipe"""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from onem2m.mec_ipe import ACTIVE, INACTIVE, Ipe, Liveness, MecRegistry, check_http, load_config

VISION = "/AE-VisionAI/fusedTracks"
STATUS = "/AE-mecIPE/MecServices/safezone-vision/status"


class FakeCse:
    """경로별 CIN 목록을 갖는 가짜 MN-CSE. down=True면 연결 오류를 낸다."""

    def __init__(self):
        self.store = {VISION: []}
        self.down = False

    def request(self, method, path="", ty=None, body=None):
        if self.down:
            raise OSError("connection refused")
        if method == "GET":
            if path.endswith("/la"):
                items = self.store.get(path[:-3])
                if not items:
                    return 404, None
                return 200, {"m2m:cin": {"ri": f"ri-{len(items)}", "con": items[-1]}}
            return (200, {}) if path in self.store else (404, None)
        if ty == 2:
            self.store["/" + body["m2m:ae"]["rn"]] = []
        elif ty == 3:
            self.store[f"{path}/{body['m2m:cnt']['rn']}"] = []
        elif ty == 4:
            if path not in self.store:
                return 404, None
            self.store[path].append(body["m2m:cin"]["con"])
        return 201, {}

    def status(self):
        return [json.loads(c) for c in self.store.get(STATUS, [])]


class Clock:
    def __init__(self, t=1_795_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


def vision_frame(cse, ts, cam_ok=True):
    cse.store[VISION].append(json.dumps({"ts": ts, "frame": 1, "cam_ok": cam_ok, "tracks": []}))


def make_ipe(cse, clock, **over):
    cfg = load_config()
    cfg.update(over)
    return Ipe(cfg, reader=cse, writer=cse, clock=clock)


class LivenessTest(unittest.TestCase):
    def test_three_failures_then_inactive_and_one_success_recovers(self):
        live = Liveness(3)
        self.assertTrue(live.observe(True, "fresh", 0))
        self.assertEqual(live.state, ACTIVE)
        self.assertFalse(live.observe(False, "stale", 1))
        self.assertFalse(live.observe(False, "stale", 2))
        self.assertTrue(live.observe(False, "stale", 3))
        self.assertEqual((live.state, live.since), (INACTIVE, 3))
        self.assertFalse(live.observe(False, "stale", 4))
        self.assertTrue(live.observe(True, "fresh", 5))
        self.assertEqual((live.state, live.fails), (ACTIVE, 0))

    def test_failure_streak_is_reset_by_success(self):
        live = Liveness(3)
        live.observe(True, "fresh", 0)
        for t, ok in enumerate([False, False, True, False, False], start=1):
            live.observe(ok, "", t)
        self.assertEqual(live.state, ACTIVE)

    def test_starting_while_service_is_down_becomes_inactive(self):
        live = Liveness(3)
        self.assertFalse(live.observe(False, "no_cin", 0))
        self.assertIsNone(live.state)
        live.observe(False, "no_cin", 1)
        self.assertTrue(live.observe(False, "no_cin", 2))
        self.assertEqual(live.state, INACTIVE)


class IpeTest(unittest.TestCase):
    def setUp(self):
        self.cse, self.clock = FakeCse(), Clock()
        self.ipe = make_ipe(self.cse, self.clock)

    def tick(self, seconds=1.0, frame=True):
        if frame:
            vision_frame(self.cse, self.clock.t)
        self.clock.t += seconds
        return self.ipe.step()

    def test_vision_stop_is_recorded_as_inactive_and_recovery_as_active(self):
        con = self.tick()
        self.assertEqual(con["state"], ACTIVE)
        self.assertIn(STATUS, self.cse.store)      # AE·CNT를 처음에 만든다
        stop = self.clock.t
        results = [self.tick(frame=False) for _ in range(5)]
        written = [r for r in results if r]
        self.assertEqual(len(written), 1)
        self.assertEqual(written[0]["state"], INACTIVE)
        self.assertTrue(written[0]["reason"].startswith("stale"))
        # 멈춘 뒤 INACTIVE까지: max_age 2초를 넘긴 뒤 연속 3번 → 약 4–5초
        self.assertLessEqual(written[0]["since"] - stop, 5.0)
        con = self.tick()
        self.assertEqual(con["state"], ACTIVE)
        self.assertEqual([s["state"] for s in self.cse.status()], [ACTIVE, INACTIVE, ACTIVE])

    def test_heartbeat_rewrites_unchanged_state(self):
        self.tick()
        for _ in range(9):
            self.assertIsNone(self.tick())
        con = self.tick()
        self.assertEqual(con["state"], ACTIVE)
        self.assertEqual(len(self.cse.status()), 2)

    def test_camera_failure_counts_as_failure(self):
        self.tick()
        for _ in range(3):
            vision_frame(self.cse, self.clock.t, cam_ok=False)
            self.clock.t += 1
            con = self.ipe.step()
        self.assertEqual((con["state"], con["reason"]), (INACTIVE, "cam_fail"))

    def test_mn_outage_is_not_counted_against_the_service(self):
        self.tick()
        self.cse.down = True
        for _ in range(5):
            self.clock.t += 1
            self.assertIsNone(self.ipe.step())   # 판단 보류: 실패로 세지 않는다
        self.assertEqual((self.ipe.live.state, self.ipe.live.fails), (ACTIVE, 0))

    def test_missing_status_container_is_recreated(self):
        self.tick()
        del self.cse.store[STATUS]
        with self.assertRaises(RuntimeError):
            for _ in range(5):
                self.tick(frame=False)
        self.assertFalse(self.ipe.ready)
        self.tick(frame=False)
        self.assertEqual(self.cse.status()[-1]["state"], INACTIVE)


class RegistryTest(unittest.TestCase):
    def test_inactive_is_pushed_to_the_mec_registry_when_enabled(self):
        entry = {"serName": "safezone-vision", "state": "ACTIVE",
                 "_links": {"self": {"href": "http://mec/services/1"}}}
        calls = []

        def http(url, method="GET", body=None, timeout_s=5):
            calls.append((method, url, body and body["state"]))
            if method == "PUT":
                entry["state"] = body["state"]
                return body
            return [dict(entry)]

        cse, clock = FakeCse(), Clock()
        ipe = make_ipe(cse, clock, mec_update=True)
        ipe.registry = MecRegistry("http://mec", "safezone-vision", 5, http=http)
        vision_frame(cse, clock.t)
        clock.t += 1
        self.assertEqual(ipe.step()["registry_state"], ACTIVE)
        con = None
        for _ in range(4):
            clock.t += 1
            con = ipe.step() or con
        self.assertEqual((con["state"], con["registry_state"]), (INACTIVE, INACTIVE))
        self.assertIn(("PUT", "http://mec/services/1", INACTIVE), calls)

    def make_discovery_ipe(self, cse, clock, endpoint, state="ACTIVE", http_error=None):
        entry = {"serName": "safezone-vision", "state": state,
                 "transportInfo": {"endpoint": {"uris": [endpoint]}}}

        def http(url, method="GET", body=None, timeout_s=5):
            if http_error:
                raise http_error
            self.assertIn("/services?ser_name=safezone-vision", url)
            return [entry]

        cfg = load_config()
        cfg.update({"probe": "mec-cin", "mn_base": "http://127.0.0.1:3000/TinyIoT-MN"})
        registry = MecRegistry("http://127.0.0.1:18080/api/v1", "safezone-vision", 1, http=http)
        return Ipe(cfg, reader=cse, writer=cse, registry=registry, clock=clock)

    def test_mec_discovery_endpoint_is_called_through_mn_cse(self):
        cse, clock = FakeCse(), Clock()
        vision_frame(cse, clock.t)
        ipe = self.make_discovery_ipe(
            cse, clock,
            "http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la",
        )
        self.assertEqual(ipe.probe(clock.t), (True, "fresh"))
        self.assertEqual(ipe.status_con(clock.t, "ACTIVE")["probe"], "mec-cin")

    def test_explicit_remote_cse_can_be_discovered_and_recovered(self):
        local, remote, clock = FakeCse(), FakeCse(), Clock()
        remote_base = "http://edge-b:3000/TinyIoT-MN"
        ipe = self.make_discovery_ipe(local, clock, remote_base + VISION + "/la")
        ipe.cfg["fail_n"] = 1
        ipe.live = Liveness(1)
        ipe.discovery_base, ipe.discovery_reader = remote_base, remote
        vision_frame(remote, clock.t)
        self.assertEqual(ipe.step()["state"], ACTIVE)
        clock.t += 10
        self.assertEqual(ipe.step()["state"], INACTIVE)
        vision_frame(remote, clock.t)
        self.assertEqual(ipe.step()["state"], ACTIVE)

    def test_discovered_cin_result_is_written_as_one_m2m_status(self):
        cse, clock = FakeCse(), Clock()
        vision_frame(cse, clock.t)
        ipe = self.make_discovery_ipe(
            cse, clock,
            "http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la",
        )
        result = ipe.step()
        self.assertEqual((result["state"], result["probe"], result["registry_state"]),
                         (ACTIVE, "mec-cin", ACTIVE))
        self.assertEqual(self.cse_status(cse)[-1]["state"], ACTIVE)

    def test_mec_service_must_be_active(self):
        cse, clock = FakeCse(), Clock()
        ipe = self.make_discovery_ipe(cse, clock, "http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la",
                                      state="INACTIVE")
        self.assertEqual(ipe.probe(clock.t), (False, "mec_service_inactive"))

    def test_mec_discovery_applies_the_same_fusedtracks_freshness_rule(self):
        cse, clock = FakeCse(), Clock()
        vision_frame(cse, clock.t - 10)
        ipe = self.make_discovery_ipe(cse, clock,
                                      "http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la")
        ipe.cfg["max_age_s"] = 2
        self.assertEqual(ipe.probe(clock.t), (False, "stale 10.0s"))

    def test_discovered_endpoint_cannot_redirect_probe_to_another_host(self):
        cse, clock = FakeCse(), Clock()
        ipe = self.make_discovery_ipe(cse, clock, "http://127.0.0.1:18081/mock-vision")
        self.assertEqual(ipe.probe(clock.t), (False, "invalid_mec_service ValueError"))

    def test_mec_registry_outage_is_indeterminate_not_service_failure(self):
        cse, clock = FakeCse(), Clock()
        ipe = self.make_discovery_ipe(
            cse, clock,
            "http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la",
            http_error=OSError("registry unavailable"),
        )
        self.assertEqual(ipe.probe(clock.t), (None, "mec_error registry unavailable"))

    @staticmethod
    def cse_status(cse):
        return cse.status()


class HttpProbeTest(unittest.TestCase):
    def test_http_probe_reports_status(self):
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):  # noqa: N802
                self.send_response(200 if self.path == "/health" else 503)
                self.end_headers()

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            self.assertEqual(check_http(base + "/health", 2), (True, "http 200"))
            self.assertEqual(check_http(base + "/down", 2), (False, "http 503"))
        finally:
            server.shutdown()
            server.server_close()
        ok, reason = check_http(base + "/health", 0.5)
        self.assertFalse(ok)
        self.assertTrue(reason.startswith("unreachable"))


if __name__ == "__main__":
    unittest.main()
