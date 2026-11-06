"""가짜 알림 수신기 — ESP8266 알림 노드(LED·부저) 대신 화면에 찍는다 (CLAUDE.md 13장).

팀 ESP 펌웨어(alert_node.ino)와 같은 규칙: 알림 con의 `level`이 `warn`·`danger`면 LED 켬, 아니면 끔.
구독 두 개를 만든다(팀의 `sub-alert-node`와 이름이 달라 서로 건드리지 않는다):
- `AE-forklift01/alert`  — 팀 설계상 ESP가 받는 곳(엔진이 아직 안 씀, 2장 빈 연결 2)
- `AE-riskengine/events` — 엔진이 지금 쓰는 곳(원래는 IN-CSE로 announce)
끝낼 때(Ctrl+C) 만든 구독을 지운다 — 남겨 두면 CSE가 없는 주소로 계속 알림을 보낸다.

  python -m vision4iot.alert_receiver --base-url http://127.0.0.1:3000          # Pi에서 (CSE와 같은 기기)
  python -m vision4iot.alert_receiver --base-url http://<Pi IP>:3000 --notify-host <노트북 IP>   # 노트북에서
"""
import argparse
import json
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from vision4iot.config import load_config
from vision4iot.onem2m import Client, cin_con

SUB_RN = "sub-alert-monitor"
WATCH = {   # 이름: (컨테이너, 구독을 만들 originator = 그 컨테이너의 AE, 팀 스크립트와 같은 방식)
    "alert": ("AE-forklift01/alert", "Cforklift01"),
    "events": ("AE-riskengine/events", "Criskengine"),
}
LED_ON_LEVELS = ("warn", "danger")       # alert_node.ino와 같음


def describe(con, now=None):
    """알림 con 한 건 → 사람이 읽는 한 줄."""
    if not isinstance(con, dict):
        return f"con 형식 모름: {con!r}"[:160]
    level = con.get("level")
    led = "LED ON " if level in LED_ON_LEVELS else "LED off"
    parts = [f"{led} level={level}"]
    if st := con.get("status"):
        parts.append(st)
    dists = [t["distance_m"] for t in con.get("targets", []) if isinstance(t, dict) and t.get("distance_m") is not None]
    if dists:
        parts.append(f"nearest {min(dists):.2f} m")
    if r := con.get("reason"):
        parts.append(f"({r})")
    if (ts := con.get("sensor_ts_unix_s")) and now and 0 <= now - ts < 60:   # 오래된 la(시험 값 등)는 지연으로 안 보임
        parts.append(f"레이더→알림 {1000 * (now - ts):.0f} ms")
    return " ".join(parts)


def make_handler(log, clock=time.time):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            name = self.path.rstrip("/").rsplit("/", 1)[-1]
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                msg = json.loads(raw or b"{}")
            except ValueError:
                msg = {}
            sgn = msg.get("m2m:sgn", {}) if isinstance(msg, dict) else {}
            if sgn.get("vrq"):
                log(f"[{name}] 구독 확인 요청(vrq) 응답")
            elif (con := cin_con(msg)) is not None:
                log(f"[{name}] {describe(con, clock())}")
            elif sgn.get("sud"):
                log(f"[{name}] 구독이 지워졌다는 알림(sud)")
            else:
                log(f"[{name}] 알 수 없는 알림: {raw[:160]!r}")
            self.send_response(200)
            self.send_header("X-M2M-RSC", "2000")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass
    return H


def main(argv=None):
    ap = argparse.ArgumentParser(description="가짜 알림 수신기 (ESP8266 LED 대신)")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--base-url", help="CSE 주소, 예 http://127.0.0.1:3000 (config onem2m.base_url 대신)")
    ap.add_argument("--port", type=int, default=8090, help="알림 받을 포트 (엔진 notification 모드는 8081)")
    ap.add_argument("--notify-host", default="127.0.0.1", help="CSE가 이 수신기에 닿는 주소 (CSE와 같은 기기면 127.0.0.1)")
    ap.add_argument("--watch", default="alert,events", help="구독할 곳: alert, events (쉼표)")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)["onem2m"]
    base = args.base_url or cfg.get("base_url")
    if not base:
        print("ERROR: CSE 주소가 없음 — --base-url http://<Pi IP>:3000", file=sys.stderr)
        return 2
    names = [n.strip() for n in args.watch.split(",") if n.strip()]
    if bad := [n for n in names if n not in WATCH]:
        print(f"ERROR: --watch {bad} (가능: {', '.join(WATCH)})", file=sys.stderr)
        return 2

    def log(s):
        print(f"{time.strftime('%H:%M:%S')} {s}", flush=True)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(log))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    made = []
    for n in names:
        path, origin = WATCH[n]
        c = Client(base, cfg["cse_name"], origin)
        c.delete(f"{path}/{SUB_RN}")                       # 지난번에 못 지운 것
        nu = f"http://{args.notify_host}:{args.port}/notify/{n}"
        status, body = c.create_sub(path, SUB_RN, nu)
        if status in (200, 201):
            made.append((c, f"{path}/{SUB_RN}"))
            log(f"구독 {path} → {nu}")
        else:
            log(f"구독 실패 {path}: HTTP {status} {json.dumps(body, ensure_ascii=False)[:160]}")
    if not made:
        server.shutdown()
        return 1
    log("가짜 알림 수신기 대기 중 (ESP8266 대신, Ctrl+C로 끝)")

    def on_term(*_):
        raise KeyboardInterrupt     # kill/timeout으로 끝나도 구독을 지운다

    signal.signal(signal.SIGTERM, on_term)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for c, p in made:
            try:
                c.delete(p)
            except OSError:
                pass
        server.shutdown()
        log("구독 지움, 종료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
