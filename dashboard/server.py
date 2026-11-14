"""SafeZone 관제 대시보드 서버. 표준 라이브러리만 사용한다.

tinyIoT CSE의 최신 CIN(`.../la`)을 주기적으로 읽어 메모리에 두고,
위험 이벤트는 JSONL 파일에 쌓아 이력·통계·핫스팟을 만든다. 브라우저는 이 서버의 /api/* 만 호출한다
(CSE 주소를 브라우저에 노출하지 않고, CORS 문제도 피한다).

CSE에는 GET .../la 와 CSEBase GET만 보낸다. CNT 하위 전체 조회(rcn=4)나 과거 CIN 개별 조회는 하지 않는다.
이력은 대시보드가 실행 중에 본 이벤트만 남는다.

실행 (저장소 루트에서):
    python -m dashboard.server --port 8080
환경 변수는 dashboard/README.md 참고.
"""

from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

LOG = logging.getLogger("safezone-dashboard")
STATIC_DIR = Path(__file__).resolve().parent / "static"
LEVELS = ("DANGER", "WARNING", "UNKNOWN", "SAFE")


def load_config() -> dict[str, Any]:
    env = os.getenv
    return {
        # 데이터를 읽을 CSE. 지금은 MN. MN→IN 이벤트 전달이 생기면 IN 주소로 바꾼다.
        "cse_base": env("DASH_CSE_BASE", "http://127.0.0.1:3000/TinyIoT-MN").rstrip("/"),
        # 상태 표시만 하는 IN-CSE (비우면 표시 안 함)
        "in_base": env("DASH_IN_BASE", "").rstrip("/"),
        "origin": env("DASH_ORIGIN", "CAdmin"),
        "rvi": env("DASH_RVI", "3"),
        "radar_path": env("DASH_RADAR_PATH", "/AE-forklift01/radar/la"),
        "events_path": env("DASH_EVENTS_PATH", "/AE-riskengine/events/la"),
        "fused_path": env("DASH_FUSED_PATH", "/AE-VisionAI/fusedTracks/la"),
        "alert_path": env("DASH_ALERT_PATH", "/AE-forklift01/alert/la"),
        "poll_s": float(env("DASH_POLL_S", "0.5")),
        "health_s": float(env("DASH_HEALTH_S", "5")),
        "timeout_s": float(env("DASH_TIMEOUT_S", "1.5")),
        "history_file": env("DASH_HISTORY", str(Path(__file__).resolve().parent / "data" / "events.jsonl")),
        "history_max": int(env("DASH_HISTORY_MAX", "5000")),
        # 핫스팟 격자 (레이더 좌표, mm)
        "grid_mm": int(env("DASH_GRID_MM", "500")),
    }


# ---------------------------------------------------------------- oneM2M 읽기

def parse_con(value: Any) -> Any:
    """con은 객체 또는 JSON 문자열(재시작 전후로 바뀔 수 있음). 둘 다 받는다."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def unwrap_cin(body: Any) -> Optional[dict[str, Any]]:
    if not isinstance(body, dict):
        return None
    cin = body.get("m2m:cin", body)
    if not isinstance(cin, dict) or "con" not in cin:
        return None
    return {"ri": cin.get("ri"), "ct": cin.get("ct"), "con": parse_con(cin.get("con"))}


class CseClient:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg

    def get(self, url: str) -> tuple[int, Any]:
        req = urllib.request.Request(url, method="GET", headers={
            "X-M2M-Origin": self.cfg["origin"],
            "X-M2M-RI": "dash-" + uuid.uuid4().hex[:12],
            "X-M2M-RVI": self.cfg["rvi"],
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=self.cfg["timeout_s"]) as res:
                raw = res.read()
                return res.status, json.loads(raw.decode("utf-8")) if raw else None
        except urllib.error.HTTPError as exc:
            return exc.code, None

    def latest(self, path: str) -> tuple[str, Optional[dict[str, Any]]]:
        """('ok'|'empty'|'error:<사유>', cin)"""
        try:
            status, body = self.get(self.cfg["cse_base"] + path)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return f"error:{type(exc).__name__}", None
        if status == 404:
            return "empty", None  # CNT가 없거나 CIN이 아직 없음
        if not 200 <= status < 300:
            return f"error:HTTP {status}", None
        cin = unwrap_cin(body)
        return ("ok", cin) if cin else ("error:not a CIN", None)

    def health(self, base: str) -> dict[str, Any]:
        started = time.monotonic()
        try:
            status, body = self.get(base)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return {"ok": False, "detail": type(exc).__name__}
        ms = round((time.monotonic() - started) * 1000)
        cb = body.get("m2m:cb", {}) if isinstance(body, dict) else {}
        return {"ok": 200 <= status < 300, "detail": f"HTTP {status}", "ms": ms,
                "rn": cb.get("rn"), "csi": cb.get("csi"), "ri": cb.get("ri")}


# ---------------------------------------------------------------- 상태 저장

class Store:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.lock = threading.Lock()
        self.sources: dict[str, dict[str, Any]] = {}
        self.health: dict[str, Any] = {}
        self.events: collections.deque = collections.deque(maxlen=cfg["history_max"])
        self.started = time.time()
        self.path = Path(cfg["history_file"])
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    self.events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        LOG.info("이력 %d건 불러옴: %s", len(self.events), self.path)

    def update_source(self, name: str, state: str, cin: Optional[dict[str, Any]]) -> bool:
        """새 CIN이면 True."""
        now = time.time()
        with self.lock:
            src = self.sources.setdefault(name, {"cin": None, "state": "init", "seen_at": None, "changed_at": None})
            src["state"], src["checked_at"] = state, now
            if cin is None:
                return False
            is_new = src["cin"] is None or cin.get("ri") != src["cin"].get("ri") or cin.get("ri") is None
            if is_new:
                src["cin"], src["changed_at"] = cin, now
            src["seen_at"] = now
            return is_new

    def add_event(self, cin: dict[str, Any], radar: Optional[dict[str, Any]]) -> None:
        con = cin["con"] if isinstance(cin["con"], dict) else {"raw": cin["con"]}
        status = str(con.get("status", "UNKNOWN")).upper()
        targets_xy = []
        # 이벤트 con에는 표적 좌표가 없다. 위험 이벤트 순간의 최신 레이더 좌표를 함께 남겨 핫스팟에 쓴다.
        if radar and status in ("WARNING", "DANGER") and isinstance(radar.get("con"), dict):
            for t in radar["con"].get("targets") or []:
                if isinstance(t, dict) and isinstance(t.get("x"), (int, float)) and isinstance(t.get("y"), (int, float)):
                    targets_xy.append([t["x"], t["y"]])
        rec = {
            "ri": cin.get("ri"), "ct": cin.get("ct"), "seen_at": time.time(), "status": status,
            "reason": con.get("reason"), "distance_m": con.get("distance_m"),
            "t_cpa_s": con.get("t_cpa_s"), "d_cpa_m": con.get("d_cpa_m"),
            "target_count": con.get("target_count"), "radar_xy_mm": targets_xy,
        }
        with self.lock:
            self.events.append(rec)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self.lock:
            out = {}
            for name, src in self.sources.items():
                out[name] = {
                    "state": src["state"],
                    "con": src["cin"]["con"] if src["cin"] else None,
                    "ri": src["cin"].get("ri") if src["cin"] else None,
                    "ct": src["cin"].get("ct") if src["cin"] else None,
                    "age_s": None if src["changed_at"] is None else round(now - src["changed_at"], 1),
                }
            return {"now": now, "sources": out, "health": dict(self.health),
                    "uptime_s": round(now - self.started)}

    def recent(self, limit: int) -> list[dict[str, Any]]:
        with self.lock:
            return list(self.events)[-limit:][::-1]

    def stats(self, since_s: float) -> dict[str, Any]:
        cutoff = time.time() - since_s
        grid = self.cfg["grid_mm"]
        counts = {k: 0 for k in LEVELS}
        cells: dict[tuple[int, int], dict[str, int]] = {}
        hourly: dict[int, dict[str, int]] = {}
        with self.lock:
            rows = [e for e in self.events if e.get("seen_at", 0) >= cutoff]
        for e in rows:
            st = e.get("status") if e.get("status") in counts else "UNKNOWN"
            counts[st] += 1
            hour = int(e["seen_at"] // 3600 * 3600)
            hourly.setdefault(hour, {k: 0 for k in LEVELS})[st] += 1
            for x, y in e.get("radar_xy_mm") or []:
                key = (int(x // grid), int(y // grid))
                c = cells.setdefault(key, {"WARNING": 0, "DANGER": 0})
                if st in c:
                    c[st] += 1
        return {
            "since_s": since_s, "total": len(rows), "counts": counts,
            "hourly": [{"hour": h, **v} for h, v in sorted(hourly.items())],
            "hotspots": sorted(
                [{"x_mm": (gx + 0.5) * grid, "y_mm": (gy + 0.5) * grid, "size_mm": grid, **v}
                 for (gx, gy), v in cells.items()],
                key=lambda c: -(c["DANGER"] * 2 + c["WARNING"]))[:50],
        }


# ---------------------------------------------------------------- polling

class Poller(threading.Thread):
    def __init__(self, cfg: dict[str, Any], store: Store, client: CseClient):
        super().__init__(daemon=True)
        self.cfg, self.store, self.client = cfg, store, client
        self.stop = threading.Event()
        self.baseline_done = False

    def poll_once(self) -> None:
        for name in ("radar", "fused", "alert"):
            state, cin = self.client.latest(self.cfg[f"{name}_path"])
            self.store.update_source(name, state, cin)
        state, cin = self.client.latest(self.cfg["events_path"])
        is_new = self.store.update_source("events", state, cin)
        # 처음 성공한 조회의 la는 대시보드 실행 전에 생긴 이벤트일 수 있다. 화면에만 보이고 이력엔 넣지 않는다.
        if is_new and cin is not None and self.baseline_done:
            with self.store.lock:
                radar = (self.store.sources.get("radar") or {}).get("cin")
            self.store.add_event(cin, radar)
        if state in ("ok", "empty"):
            self.baseline_done = True

    def check_health(self) -> None:
        health = {"mn": self.client.health(self.cfg["cse_base"])}
        if self.cfg["in_base"]:
            health["in"] = self.client.health(self.cfg["in_base"])
        with self.store.lock:
            self.store.health = health

    def run(self) -> None:
        next_health = 0.0
        while not self.stop.is_set():
            started = time.monotonic()
            if started >= next_health:
                self.check_health()
                next_health = started + self.cfg["health_s"]
            try:
                self.poll_once()
            except Exception:  # 한 번 실패로 대시보드가 멈추지 않게 한다
                LOG.exception("polling 오류")
            self.stop.wait(max(0.0, self.cfg["poll_s"] - (time.monotonic() - started)))


# ---------------------------------------------------------------- HTTP

def make_handler(store: Store, cfg: dict[str, Any]):
    public_cfg = {k: cfg[k] for k in ("cse_base", "in_base", "radar_path", "events_path", "fused_path",
                                      "alert_path", "poll_s", "grid_mm")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.debug(fmt, *args)

        def _json(self, obj: Any, code: int = 200) -> None:
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if url.path in ("/", "/index.html"):
                body = (STATIC_DIR / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif url.path == "/api/state":
                self._json({**store.snapshot(), "config": public_cfg})
            elif url.path == "/api/events":
                limit = max(1, min(500, int(q.get("limit", ["50"])[0])))
                self._json(store.recent(limit))
            elif url.path == "/api/stats":
                hours = max(0.1, min(24 * 30, float(q.get("hours", ["24"])[0])))
                self._json(store.stats(hours * 3600))
            else:
                self._json({"error": "not found"}, 404)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="SafeZone 관제 대시보드")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config()
    store = Store(cfg)
    Poller(cfg, store, CseClient(cfg)).start()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(store, cfg))
    LOG.info("대시보드: http://%s:%d  (CSE %s)", args.host, args.port, cfg["cse_base"])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
