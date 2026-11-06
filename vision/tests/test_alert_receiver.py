"""가짜 알림 수신기 시험 — tinyIoT 구독 알림 형식(m2m:sgn)을 HTTP로 보내 본다."""
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from vision4iot.alert_receiver import describe, make_handler
from vision4iot.onem2m import cin_con

EVENT = {"schema": "safezone.risk-event.v1", "status": "DANGER", "level": "danger", "reason": "distance_danger",
         "sensor_ts_unix_s": 100.0, "targets": [{"distance_m": 1.02}, {"distance_m": 4.7}, {"distance_m": None}]}


def sgn(con):
    return {"m2m:sgn": {"nev": {"rep": {"m2m:cin": {"con": con}}, "net": 3}, "sur": "TinyIoT/x/sub"}}


def test_cin_con_accepts_string_or_object_and_plain_cin():
    assert cin_con(sgn(json.dumps(EVENT)))["level"] == "danger"     # 엔진은 con을 JSON 문자열로 쓴다
    assert cin_con(sgn({"level": "warn"})) == {"level": "warn"}
    assert cin_con({"m2m:cin": {"con": '{"a":1}'}}) == {"a": 1}       # la GET 응답
    assert cin_con(sgn("on")) == {"raw": "on"}                         # 팀 demo.sh의 con "on"
    assert cin_con({"m2m:sgn": {"vrq": True}}) is None


def test_describe_follows_esp_led_rule():
    line = describe(EVENT, now=100.25)
    assert line.startswith("LED ON  level=danger") and "nearest 1.02 m" in line and "250 ms" in line
    assert describe({"level": "warn"}).startswith("LED ON")
    for lv in ("safe", "unknown", None):
        assert describe({"level": lv}).startswith("LED off")


@pytest.fixture
def receiver():
    logs = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(logs.append, clock=lambda: 100.1))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", logs
    srv.shutdown()


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.status, r.headers["X-M2M-RSC"]


def test_receiver_answers_2000_and_logs_by_watch_name(receiver):
    url, logs = receiver
    assert post(f"{url}/notify/events", sgn(json.dumps(EVENT))) == (200, "2000")
    assert post(f"{url}/notify/alert", {"m2m:sgn": {"vrq": True}}) == (200, "2000")
    assert logs[0].startswith("[events] LED ON  level=danger") and "100 ms" in logs[0]
    assert logs[1] == "[alert] 구독 확인 요청(vrq) 응답"
