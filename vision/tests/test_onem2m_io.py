"""tinyIoT 읽기(레이더 la)와 쓰기(fusedTracks) 시험 — 가짜 CSE(진짜 HTTP 서버)로."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from vision4iot.onem2m import Client
from vision4iot.publisher import OneM2MPublisher
from vision4iot.radar.onem2m_in import OneM2MRadar


class FakeCSE:
    def __init__(self):
        self.la = None              # GET .../radar/la 응답 (dict) 또는 None → 404
        self.la_status = 200
        self.posts = []
        self.exists = set()
        outer = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, obj):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                if outer.la is None:
                    return self._send(404, {"m2m:dbg": "not found"})
                self._send(outer.la_status, outer.la if outer.la_status == 200 else {"m2m:dbg": "no privilege"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                ty = self.headers["Content-Type"].split("ty=")[-1]
                outer.posts.append((self.path, self.headers["X-M2M-Origin"], ty, body))
                key = (self.path, json.dumps(body)) if ty in ("2", "3") else None
                if key and key in outer.exists:
                    return self._send(409, {"m2m:dbg": "already exists"})
                if key:
                    outer.exists.add(key)
                self._send(201, body)

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()


@pytest.fixture
def cse():
    c = FakeCSE()
    yield c
    c.close()


def cin(ri, targets, as_string=True):
    con = {"ts": 1.0, "targets": targets}
    return {"m2m:cin": {"ri": ri, "con": json.dumps(con) if as_string else con}}


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def test_radar_reader_ignores_startup_la_then_converts_units(cse):
    clk = Clock()
    r = OneM2MRadar(Client(cse.url, "TinyIoT", "CVisionAI"), "AE-forklift01/radar", clock=clk)
    cse.la = cin("4-1", [{"x": 500, "y": 1500, "v": -50}])
    r.poll_once()
    assert r.get() == ([], False)              # 시작 때 이미 있던 la는 오래된 값일 수 있어 안 씀
    cse.la = cin("4-2", [{"x": 500, "y": 1500, "v": -50}], as_string=False)
    r.poll_once()
    targets, ok = r.get()
    assert ok and len(targets) == 1
    t = targets[0]
    assert (t.x, t.y, t.v) == (0.5, 1.5, -0.5)  # mm → m, cm/s → m/s
    clk.t += 1.5                               # 1초 넘게 새 CIN 없음 → stale
    r.poll_once()                              # 같은 ri → 갱신 안 됨
    assert r.get() == ([], False)


def test_radar_reader_reports_missing_privilege(cse):
    r = OneM2MRadar(Client(cse.url, "TinyIoT", "CVisionAI"), "AE-forklift01/radar")
    cse.la, cse.la_status = cin("4-1", []), 403
    r.poll_once()
    assert "403" in r.last_error and "ACP" in r.last_error


def test_publisher_creates_ae_and_cnt_then_posts_string_con(cse):
    pub = OneM2MPublisher(Client(cse.url, "TinyIoT", "CVisionAI"), "AE-VisionAI/fusedTracks", log=lambda s: None)
    msg = {"ts": 1.0, "frame": 1, "cam_ok": True, "latency_ms": 5, "tracks": []}
    pub.publish(msg)
    for _ in range(50):
        if pub.sent:
            break
        time.sleep(0.02)
    pub.close()
    (p1, o1, t1, b1), (p2, _, t2, b2), (p3, _, t3, b3) = cse.posts[:3]
    assert (p1, o1, t1) == ("/TinyIoT", "CVisionAI", "2") and b1["m2m:ae"]["rn"] == "AE-VisionAI"
    assert (p2, t2) == ("/TinyIoT/AE-VisionAI", "3") and b2["m2m:cnt"] == {"rn": "fusedTracks", "mni": 100}
    assert (p3, t3) == ("/TinyIoT/AE-VisionAI/fusedTracks", "4")
    assert json.loads(b3["m2m:cin"]["con"]) == msg
    # 다시 시작해도(409) 그대로 쓴다
    OneM2MPublisher(Client(cse.url, "TinyIoT", "CVisionAI"), "AE-VisionAI/fusedTracks", log=lambda s: None).close()
