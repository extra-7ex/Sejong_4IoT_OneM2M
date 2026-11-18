"""python3 -m unittest onem2m.test_measure_latency"""

import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from onem2m.measure_latency import Meter, ct_to_unix, make_handler, nearest_m


def radar(ts, *mm):
    return {"ts": ts, "targets": [{"x": x, "y": y} for x, y in mm]}


class MeterTest(unittest.TestCase):
    def test_engine_path_measures_from_first_frame_inside(self):
        m = Meter("danger", 0.5)
        m.on_radar(radar(100.0, (0, 1200)), 100.05)
        m.on_radar(radar(100.5, (0, 400)), 100.56)            # 진입
        m.on_radar(radar(101.0, (0, 300)), 101.05)            # 같은 진입의 다음 프레임은 무시
        row = m.on_alert({"level": "danger"}, "19700101T000141,200", 101.30)
        self.assertEqual((row["total_s"], row["upload_s"], row["decide_s"]), (0.8, 0.06, 0.74))
        self.assertEqual(row["alert_store_s"], 0.7)
        self.assertIsNone(m.on_alert({"level": "danger"}, None, 101.5))   # 같은 진입에 두 번 기록하지 않음

    def test_each_entry_is_measured_separately_and_missed_entries_counted(self):
        m = Meter("danger", 0.5)
        m.on_radar(radar(1, (0, 400)), 1.05)
        m.on_alert({"level": "danger"}, None, 1.4)
        m.on_radar(radar(2, ), 2.05)                           # 구역을 벗어남
        m.on_radar(radar(3, (100, 300)), 3.05)                 # 다시 진입
        m.on_alert({"level": "warn"}, None, 3.2)               # 다른 단계는 무시
        m.on_alert({"level": "danger"}, None, 3.5)
        m.on_radar(radar(4, (0, 450)), 4.05)
        m.on_radar(radar(5, (0, 2000)), 5.05)
        m.on_radar(radar(6, (0, 400)), 6.05)                   # alert 없이 나간 진입
        m.on_radar(radar(7, ), 7.05)
        self.assertEqual([r["total_s"] for r in m.results], [0.4, 0.5])
        self.assertEqual(m.missed, 1)
        self.assertIn("측정 2건", m.summary())

    def test_alert_before_radar_cin_is_paired_when_node_decides_locally(self):
        m = Meter("danger", 0.5)
        m.on_alert({"level": "danger"}, None, 10.20)           # 레이더 노드가 프레임마다 판단해 먼저 기록
        m.on_radar(radar(10.30, (0, 400)), 10.35)
        self.assertEqual(m.results[0]["total_s"], -0.1)

    def test_helpers(self):
        self.assertAlmostEqual(nearest_m(radar(0, (300, 400), (0, 2000))), 0.5)
        self.assertIsNone(nearest_m(radar(0)))
        self.assertAlmostEqual(ct_to_unix("19700101T000001,250"), 1.25)
        self.assertIsNone(ct_to_unix("bad"))


class HandlerTest(unittest.TestCase):
    def test_notifications_over_http(self):
        m, rows = Meter("danger", 0.5), []
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(m, rows.append))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"

        def post(path, body):
            req = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=2) as res:
                return res.status

        try:
            self.assertEqual(post("/radar", {"m2m:sgn": {"vrq": True}}), 200)
            post("/radar", {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {"con": json.dumps(radar(1e9, (0, 300)))}}}}})
            post("/alert", {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {"con": '{"level":"danger"}'}}}}})
        finally:
            server.shutdown()
            server.server_close()
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
