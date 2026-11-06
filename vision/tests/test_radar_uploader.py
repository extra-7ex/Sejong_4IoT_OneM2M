"""레이더 업로더 시험 — 진짜 HTTP 서버(가짜 CSE)에 보내 헤더·주소·con 형식을 확인한다."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from vision4iot.onem2m import Client
from vision4iot.radar.base import Target
from vision4iot.radar_uploader import http_sender, run


class FakeCSE:
    """POST를 기록하고 정해 둔 상태 코드로 답한다."""

    def __init__(self, status=201):
        self.requests = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append((self.path, self.headers, json.loads(body)))   # 헤더 이름은 대소문자 무관
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"m2m:dbg":"x"}' if outer.status >= 400 else b'{"m2m:cin":{}}')

            def log_message(self, *a):
                pass

        self.status = status
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


def test_post_cin_uses_team_headers_and_path(cse):
    c = Client(cse.url, "TinyIoT", "Cforklift01")
    status, _ = c.post_cin("AE-forklift01/radar", {"ts": 1.0, "targets": []})
    assert status == 201
    path, h, body = cse.requests[0]
    assert path == "/TinyIoT/AE-forklift01/radar"
    assert h["X-M2M-Origin"] == "Cforklift01" and h["X-M2M-RVI"] == "3"
    assert h["Content-Type"] == "application/json;ty=4" and h["Accept"] == "application/json"
    assert body == {"m2m:cin": {"con": '{"ts":1.0,"targets":[]}'}}   # tinyIoT는 con을 문자열로만 받는다
    c.post_cin("AE-forklift01/radar", {})
    assert cse.requests[0][1]["X-M2M-RI"] != cse.requests[1][1]["X-M2M-RI"]   # 요청마다 다른 RI


class Fixed:
    def __init__(self, targets):
        self.targets = targets

    def get_targets(self, ts):
        return self.targets


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_run_sends_at_rate_including_empty_targets(cse):
    clock, logs = FakeClock(), []
    send = http_sender(Client(cse.url, "TinyIoT", "Cforklift01"), "AE-forklift01/radar")
    sent, ok = run(Fixed([]), "sim", send, hz=10, duration=2.0, clock=clock, sleep=clock.sleep, log=logs.append)
    assert sent == ok == 20                                   # 2초 × 10 Hz
    cons = [json.loads(b["m2m:cin"]["con"]) for _, _, b in cse.requests]
    assert all(c["targets"] == [] and c["src"] == "sim" for c in cons)   # 사람이 없어도 매번, sim 표시
    assert len(logs) == 1 and logs[0].startswith("[SIM] targets 0")   # 1초마다 요약 한 줄 (2초째 직전에 끝남)


def test_run_converts_to_team_units(cse):
    clock = FakeClock()
    send = http_sender(Client(cse.url, "TinyIoT", "Cforklift01"), "AE-forklift01/radar")
    run(Fixed([Target(0, 0.2, 1.0, -0.5)]), "sim", send, hz=10, duration=0.05, clock=clock, sleep=clock.sleep,
        log=lambda s: None)
    con = json.loads(cse.requests[0][2]["m2m:cin"]["con"])
    assert con["targets"] == [{"x": 200, "y": 1000, "v": -50}] and con["ts"] == 1000.0


def test_missing_container_hints_team_setup_script():
    bad = FakeCSE(status=404)
    try:
        send = http_sender(Client(bad.url, "TinyIoT", "Cforklift01"), "AE-forklift01/radar")
        ok, msg = send({"ts": 1.0, "targets": []})
        assert not ok and "404" in msg and "setup_onem2m.sh" in msg
    finally:
        bad.close()


def test_cse_down_is_reported_not_raised():
    send = http_sender(Client("http://127.0.0.1:9", "TinyIoT", "Cforklift01", timeout=0.5), "AE-forklift01/radar")
    ok, msg = send({"ts": 1.0, "targets": []})
    assert not ok and "연결 안 됨" in msg


def test_client_requires_base_url():
    with pytest.raises(ValueError):
        Client("", "TinyIoT", "Cforklift01")
