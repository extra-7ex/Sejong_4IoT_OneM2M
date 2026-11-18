"""감지 → 정지 지연 측정. 표준 라이브러리만 사용한다. Pi에서 실행한다.

레이더 CNT와 alert CNT에 시험용 구독(SUB)을 만들고, 이 프로그램이 ESP 대신 알림을 받는다.
사람이 위험 거리(기본 0.5 m) 안으로 들어올 때마다 다음을 잰다.

    radar ts            레이더 노드가 이 프레임을 읽은 시각 (레이더 CIN의 ts, Pi 시계)
    → 레이더 알림 도착    CSE에 저장된 레이더 CIN 알림이 이 프로그램에 온 시각     (= 업로드)
    → danger alert 도착  alert CIN(level=danger) 알림이 이 프로그램에 온 시각       (= 판단·기록)
    합계 = danger alert 도착 − radar ts

ESP도 같은 alert 알림을 같은 순간에 받으므로, 합계에 Wi-Fi 전달과 서보 정지(수십 ms)를 더하면
실제 "감지에서 정지까지"다. 레이더는 0.5초마다 업로드하므로 사람이 들어선 순간이 업로드 사이였다면
최대 그만큼 더 걸릴 수 있다(결과에 함께 표시).

실행 (저장소 루트, Pi):
    python3 -m onem2m.measure_latency                  # Ctrl+C로 끝내면 요약과 SUB 정리
    python3 -m onem2m.measure_latency --count 10 --csv logs/latency.csv
    python3 -m onem2m.measure_latency --level warn --threshold-m 1.0
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import statistics
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from onem2m.mn_to_in_bridge import Cse, parse_con

UPLOAD_INTERVAL_S = 0.5   # radar_node.py의 UPLOAD_INTERVAL


def nearest_m(con: Any) -> Optional[float]:
    """레이더 con(mm)에서 가장 가까운 표적까지 거리(m). 표적이 없으면 None."""
    targets = con.get("targets") if isinstance(con, dict) else None
    dists = [math.hypot(t["x"], t["y"]) / 1000 for t in targets or []
             if isinstance(t, dict) and isinstance(t.get("x"), (int, float)) and isinstance(t.get("y"), (int, float))]
    return min(dists) if dists else None


def ct_to_unix(ct: Any) -> Optional[float]:
    """tinyIoT ct '20261118T144116,705'(UTC) → Unix 초."""
    if not isinstance(ct, str):
        return None
    try:
        main, _, frac = ct.partition(",")
        t = dt.datetime.strptime(main, "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc).timestamp()
        return t + (float("0." + frac) if frac.isdigit() else 0.0)
    except ValueError:
        return None


class Meter:
    """레이더·alert 알림을 받아 위험 구역 진입마다 지연을 한 건씩 기록한다."""

    def __init__(self, level: str = "danger", threshold_m: float = 0.5, pair_window_s: float = 1.0):
        self.level, self.threshold_m, self.pair_window_s = level, threshold_m, pair_window_s
        self.in_zone = False
        self.detect: Optional[dict] = None       # 이번 진입의 첫 레이더 프레임
        self.early_alert: Optional[dict] = None  # 레이더 CIN보다 먼저 온 alert (레이더 노드가 직접 판단할 때)
        self.results: list[dict] = []
        self.missed = 0                          # 구역에 들어왔다 나갔는데 alert가 없던 횟수
        self.lock = threading.Lock()

    def on_radar(self, con: Any, arrival: float) -> None:
        with self.lock:
            near = nearest_m(con)
            ts = con.get("ts") if isinstance(con, dict) else None
            inside = near is not None and near <= self.threshold_m
            if inside and not self.in_zone and isinstance(ts, (int, float)):
                self.in_zone = True
                self.detect = {"radar_ts": float(ts), "radar_arrival": arrival, "distance_m": round(near, 3)}
                early = self.early_alert
                self.early_alert = None
                if early and arrival - early["alert_arrival"] <= self.pair_window_s:
                    self._record(early)
            elif not inside and self.in_zone:
                self.in_zone = False
                if self.detect and not self.detect.get("paired"):
                    self.missed += 1
                self.detect = None

    def on_alert(self, con: Any, ct: Any, arrival: float) -> Optional[dict]:
        with self.lock:
            level = con.get("level") if isinstance(con, dict) else None
            if level != self.level:
                return None
            alert = {"alert_arrival": arrival, "alert_ct": ct_to_unix(ct)}
            if self.detect and not self.detect.get("paired"):
                return self._record(alert)
            if not self.in_zone:
                self.early_alert = alert
            return None

    def _record(self, alert: dict) -> dict:
        d = self.detect
        d["paired"] = True
        row = {
            "n": len(self.results) + 1,
            "distance_m": d["distance_m"],
            "radar_ts": round(d["radar_ts"], 3),
            "upload_s": round(d["radar_arrival"] - d["radar_ts"], 3),
            "decide_s": round(alert["alert_arrival"] - d["radar_arrival"], 3),
            "total_s": round(alert["alert_arrival"] - d["radar_ts"], 3),
            "alert_store_s": None if alert["alert_ct"] is None else round(alert["alert_ct"] - d["radar_ts"], 3),
        }
        self.results.append(row)
        return row

    def summary(self) -> str:
        totals = [r["total_s"] for r in self.results]
        if not totals:
            return f"측정 0건 (alert 없이 끝난 진입 {self.missed}회)"
        med = statistics.median(totals)
        return (f"측정 {len(totals)}건: 합계 중앙값 {med:.2f}초, 최소 {min(totals):.2f}, 최대 {max(totals):.2f} "
                f"(업로드 간격 때문에 최대 +{UPLOAD_INTERVAL_S:.1f}초 가능, alert 없이 끝난 진입 {self.missed}회)")


def make_handler(meter: Meter, on_row):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802
            arrival = time.time()
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
            self.send_response(200)
            self.send_header("X-M2M-RSC", "2000")
            self.end_headers()
            try:
                sgn = json.loads(raw.decode("utf-8")).get("m2m:sgn", {})
            except (ValueError, AttributeError):
                return
            if sgn.get("vrq"):
                return                                   # 구독 확인 요청
            cin = ((sgn.get("nev") or {}).get("rep") or {}).get("m2m:cin")
            if not isinstance(cin, dict):
                return
            con = parse_con(cin.get("con"))
            if self.path.startswith("/radar"):
                meter.on_radar(con, arrival)
            elif self.path.startswith("/alert"):
                row = meter.on_alert(con, cin.get("ct"), arrival)
                if row:
                    on_row(row)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description="감지 → 정지 지연 측정 (Pi에서 실행)")
    ap.add_argument("--cse", default="http://127.0.0.1:3000/TinyIoT-MN")
    ap.add_argument("--origin", default="Cforklift01", help="SUB를 만들 originator (AE-forklift01 소유자)")
    ap.add_argument("--radar", default="/AE-forklift01/radar")
    ap.add_argument("--alert", default="/AE-forklift01/alert")
    ap.add_argument("--listen", default="127.0.0.1", help="알림을 받을 주소 (CSE가 닿는 주소)")
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--level", default="danger", choices=("danger", "warn"))
    ap.add_argument("--threshold-m", type=float, default=0.5, help="이 거리 안이면 위험 구역 진입 (radar_node DANGER_MM과 맞춤)")
    ap.add_argument("--count", type=int, default=0, help="이만큼 재면 끝 (0이면 Ctrl+C까지)")
    ap.add_argument("--csv", help="결과를 CSV로 저장")
    args = ap.parse_args()

    meter = Meter(args.level, args.threshold_m)
    done = threading.Event()

    def on_row(row: dict) -> None:
        extra = "" if row["alert_store_s"] is None else f", alert 저장 {row['alert_store_s']:.2f}s"
        print(f"#{row['n']} {row['distance_m']:.2f} m 진입 → {args.level} alert {row['total_s']:.2f}s "
              f"(업로드 {row['upload_s']:.2f}s + 판단·기록 {row['decide_s']:.2f}s{extra})", flush=True)
        if args.count and row["n"] >= args.count:
            done.set()

    server = ThreadingHTTPServer((args.listen, args.port), make_handler(meter, on_row))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    cse = Cse(args.cse, args.origin, "3", 10)
    tag = uuid.uuid4().hex[:6]
    subs = []
    try:
        for cnt, path in ((args.radar, "radar"), (args.alert, "alert")):
            rn = f"sub-latency-{path}-{tag}"
            status, body = cse.request("POST", cnt, 23, {"m2m:sub": {
                "rn": rn, "nu": [f"http://{args.listen}:{args.port}/{path}"], "nct": 1, "enc": {"net": [3]}}})
            if status not in (200, 201):
                raise SystemExit(f"{cnt} 구독 실패: HTTP {status} {str(body)[:160]}")
            subs.append(f"{cnt}/{rn}")
        print(f"측정 중: {args.threshold_m} m 안으로 들어오면 {args.level} alert까지 잽니다 (Ctrl+C로 종료)", flush=True)
        while not done.wait(0.5):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        for sub in subs:
            cse.request("DELETE", sub)
        server.shutdown()
        print(meter.summary())
        if args.csv and meter.results:
            with open(args.csv, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(meter.results[0]))
                w.writeheader()
                w.writerows(meter.results)
            print(f"CSV: {args.csv}")


if __name__ == "__main__":
    main()
