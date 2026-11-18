"""대시보드 시험용 가짜 CSE. 실제 tinyIoT 없이 화면을 확인할 때만 쓴다.

사람 1명이 지게차 쪽으로 다가왔다 멀어지는 상황을 반복한다.
radar/la, events/la(상태가 바뀔 때만 새 CIN), fusedTracks/la, CSEBase GET에 응답한다.

    python -m dashboard.fake_cse --port 3900
    DASH_CSE_BASE=http://127.0.0.1:3900/TinyIoT-MN python -m dashboard.server
"""

from __future__ import annotations

import argparse
import json
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

T0 = time.time()
STATE = {"status": None, "events": [], "seq": 0}


def target_at(t: float) -> tuple[float, float, float]:
    """30초 주기로 5.5 m → 0.8 m → 5.5 m 왕복. (x_mm, y_mm, v_cm_s)"""
    phase = (t % 30) / 30
    d = 0.8 + 4.7 * abs(math.cos(math.pi * phase))
    x = 0.6 * math.sin(2 * math.pi * phase)
    v = -4.7 * math.pi / 30 * math.sin(math.pi * phase) * (1 if phase < 0.5 else -1) * 100
    return x * 1000, d * 1000, v


def current() -> dict:
    now = time.time()
    x, y, v = target_at(now - T0)
    d = math.hypot(x, y) / 1000
    status = "DANGER" if d <= 1.5 else "WARNING" if d <= 3.0 else "SAFE"
    if status != STATE["status"]:
        STATE["status"] = status
        STATE["seq"] += 1
        con = {"schema": "safezone.risk-event.v1", "status": status, "reason": "current_distance_" + status.lower(),
               "distance_m": round(d, 3), "t_cpa_s": None, "d_cpa_m": None, "target_count": 1,
               "parameters": {"warning_distance_m": 3.0, "danger_distance_m": 1.5}}
        STATE["events"].append({"ri": f"cin-ev{STATE['seq']}", "ct": time.strftime("%Y%m%dT%H%M%S"),
                                "con": json.dumps(con)})
    radar = {"ri": f"cin-r{int(now * 10)}", "con": json.dumps({"ts": round(now, 2), "targets": [{"x": round(x), "y": round(y), "v": round(v)}]})}
    fused = {"ri": f"cin-f{int(now * 10)}", "con": {"ts": now, "cam_ok": True, "tracks": [
        {"id": 0, "state": "confirmed", "x": round(x / 1000 + 0.05, 2), "y": round(y / 1000 - 0.05, 2), "posture": "standing"}]}}
    return {"radar": radar, "fused": fused, "events": STATE["events"][-1] if STATE["events"] else None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def do_GET(self) -> None:  # noqa: N802
        cur = current()
        path = self.path.split("?")[0]
        body = None
        if path.endswith("/radar/la"):
            body = {"m2m:cin": cur["radar"]}
        elif path.endswith("/fusedTracks/la"):
            body = {"m2m:cin": cur["fused"]}
        elif path.endswith("/events/la") and cur["events"]:
            body = {"m2m:cin": cur["events"]}
        elif path.count("/") == 1:
            body = {"m2m:cb": {"rn": path.strip("/"), "ri": "id-mn", "csi": "/id-mn"}}
        if body is None:
            self.send_response(404)
            self.send_header("X-M2M-RSC", "4004")
            self.end_headers()
            return
        raw = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-M2M-RSC", "2000")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=3900)
    args = ap.parse_args()
    print(f"fake CSE: http://127.0.0.1:{args.port}/TinyIoT-MN")
    ThreadingHTTPServer(("0.0.0.0", args.port), Handler).serve_forever()
