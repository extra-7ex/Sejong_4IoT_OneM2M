"""MN → IN 위험 이벤트 브리지. 표준 라이브러리만 사용한다.

MN-CSE의 RiskEngine 이벤트(`AE-riskengine/events/la`)를 0.5초마다 확인해서,
새 이벤트가 생기면 IN-CSE의 `AE-safezone/events`에 요약 CIN으로 올린다.
현장 판단은 MN(엣지)에서 하고, 클라우드(IN)에는 이력만 쌓는 구조다.

IN에는 이력 조회에 필요한 필드만 담은 요약을 저장한다(CIN 하나 255바이트 이하).
저장량을 줄이고, 대시보드가 IN 이력 전체를 한 번에 불러와도 가볍게 하기 위해서다.

실행 (저장소 루트에서):
    python3 -m onem2m.mn_to_in_bridge
    python3 -m onem2m.mn_to_in_bridge --once     # 한 번만 확인하고 종료 (시험용)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

LOG = logging.getLogger("mn-to-in-bridge")
MAX_CON_BYTES = 255


def load_config() -> dict[str, Any]:
    env = os.getenv
    return {
        "mn_base": env("BRIDGE_MN_BASE", "http://127.0.0.1:3000/TinyIoT-MN").rstrip("/"),
        "in_base": env("BRIDGE_IN_BASE", "http://127.0.0.1:3001/TinyIoT").rstrip("/"),
        "mn_origin": env("BRIDGE_MN_ORIGIN", "CAdmin"),            # MN 조회용
        "in_origin": env("BRIDGE_IN_ORIGIN", "Csafezone"),          # IN AE 생성·기록용
        "events_path": env("BRIDGE_EVENTS_PATH", "/AE-riskengine/events/la"),
        "radar_path": env("BRIDGE_RADAR_PATH", "/AE-forklift01/radar/la"),
        "in_ae": env("BRIDGE_IN_AE", "AE-safezone"),
        "in_cnt": env("BRIDGE_IN_CNT", "events"),
        "in_mni": int(env("BRIDGE_IN_MNI", "5000")),
        "rvi": env("BRIDGE_RVI", "3"),
        "poll_s": float(env("BRIDGE_POLL_S", "0.5")),
        "timeout_s": float(env("BRIDGE_TIMEOUT_S", "2")),
        "state_file": env("BRIDGE_STATE", str(Path.home() / ".safezone_bridge_state.json")),
    }


class Cse:
    def __init__(self, base: str, origin: str, rvi: str, timeout_s: float):
        self.base, self.origin, self.rvi, self.timeout_s = base, origin, rvi, timeout_s

    def request(self, method: str, path: str = "", ty: Optional[int] = None,
                body: Optional[dict] = None) -> tuple[int, Any]:
        headers = {"X-M2M-Origin": self.origin, "X-M2M-RI": "br-" + uuid.uuid4().hex[:12],
                   "X-M2M-RVI": self.rvi, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = f"application/json;ty={ty}" if ty else "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw) if raw else None
            except ValueError:
                return exc.code, None


def parse_con(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def latest_cin(cse: Cse, path: str) -> Optional[dict]:
    status, body = cse.request("GET", path)
    if status == 404:
        return None
    if not 200 <= status < 300 or not isinstance(body, dict) or "m2m:cin" not in body:
        raise RuntimeError(f"GET {path} → HTTP {status} {str(body)[:120]}")
    cin = body["m2m:cin"]
    return {"ri": cin.get("ri"), "con": parse_con(cin.get("con"))}


def _num(v: Any, nd: int) -> Any:
    return round(v, nd) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def summarize(event: dict, mn_ri: Optional[str], radar: Optional[dict]) -> str:
    """RiskEngine 이벤트(약 1.4 KB)를 IN 이력용 요약 JSON 문자열(255바이트 이하)로 줄인다."""
    con = event if isinstance(event, dict) else {}
    status = str(con.get("status", "UNKNOWN")).upper()
    ts = con.get("sensor_ts_unix_s") or con.get("server_received_at_unix_s") or time.time()
    out: dict[str, Any] = {
        "ts": round(float(ts), 2),
        "status": status,
        "reason": str(con.get("reason") or "")[:40],
        "distance_m": _num(con.get("distance_m"), 2),
        "t_cpa_s": _num(con.get("t_cpa_s"), 2),
        "d_cpa_m": _num(con.get("d_cpa_m"), 2),
        "n": con.get("target_count") if isinstance(con.get("target_count"), int) else None,
    }
    # 위험 이벤트 순간의 레이더 좌표(mm). 대시보드 핫스팟에 쓴다.
    if status in ("WARNING", "DANGER") and radar and isinstance(radar.get("con"), dict):
        xy = [[int(t["x"]), int(t["y"])] for t in radar["con"].get("targets") or []
              if isinstance(t, dict) and isinstance(t.get("x"), (int, float)) and isinstance(t.get("y"), (int, float))]
        if xy:
            out["xy_mm"] = xy[:3]
    if mn_ri:
        out["mn_ri"] = mn_ri
    text = json.dumps(out, separators=(",", ":"), ensure_ascii=True)
    # 길이 초과 시 덜 중요한 것부터 뺀다
    for drop in ("mn_ri", "xy_mm", "reason"):
        if len(text.encode()) <= MAX_CON_BYTES:
            break
        out.pop(drop, None)
        text = json.dumps(out, separators=(",", ":"), ensure_ascii=True)
    return text


class Bridge:
    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        self.mn = Cse(cfg["mn_base"], cfg["mn_origin"], cfg["rvi"], cfg["timeout_s"])
        self.inn = Cse(cfg["in_base"], cfg["in_origin"], cfg["rvi"], cfg["timeout_s"])
        self.state_path = Path(cfg["state_file"])
        self.last_ri: Optional[str] = self._load_state()
        self.ready = False
        self.sent = 0

    def _load_state(self) -> Optional[str]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8")).get("last_mn_ri")
        except (OSError, ValueError):
            return None

    def _save_state(self) -> None:
        try:
            self.state_path.write_text(json.dumps({"last_mn_ri": self.last_ri}), encoding="utf-8")
        except OSError as exc:
            LOG.warning("상태 파일 저장 실패: %s", exc)

    def ensure_in_resources(self) -> None:
        """IN에 AE·CNT가 없으면 만든다. 이미 있으면 그대로 쓴다."""
        ae, cnt = self.cfg["in_ae"], self.cfg["in_cnt"]
        status, _ = self.inn.request("GET", f"/{ae}")
        if status == 404:
            status, body = self.inn.request("POST", "", 2, {"m2m:ae": {
                "rn": ae, "api": "Nsafezone", "rr": True, "srv": ["3"]}})
            if status not in (200, 201):
                raise RuntimeError(f"IN AE 생성 실패: HTTP {status} {body}")
            LOG.info("IN에 %s 생성", ae)
        elif not 200 <= status < 300:
            raise RuntimeError(f"IN AE 조회 실패: HTTP {status} (originator {self.cfg['in_origin']} 권한 확인)")
        status, _ = self.inn.request("GET", f"/{ae}/{cnt}")
        if status == 404:
            status, body = self.inn.request("POST", f"/{ae}", 3, {"m2m:cnt": {"rn": cnt, "mni": self.cfg["in_mni"]}})
            if status not in (200, 201):
                raise RuntimeError(f"IN CNT 생성 실패: HTTP {status} {body}")
            LOG.info("IN에 %s/%s 생성 (mni %d)", ae, cnt, self.cfg["in_mni"])
        elif not 200 <= status < 300:
            raise RuntimeError(f"IN CNT 조회 실패: HTTP {status}")
        self.ready = True

    def step(self) -> bool:
        """새 이벤트를 IN에 올렸으면 True."""
        if not self.ready:
            self.ensure_in_resources()
        event = latest_cin(self.mn, self.cfg["events_path"])
        if event is None or event["ri"] == self.last_ri:
            return False
        try:
            radar = latest_cin(self.mn, self.cfg["radar_path"])
        except RuntimeError:
            radar = None
        con = summarize(event["con"], event["ri"], radar)
        status, body = self.inn.request("POST", f"/{self.cfg['in_ae']}/{self.cfg['in_cnt']}", 4,
                                        {"m2m:cin": {"con": con}})
        if status not in (200, 201):
            if status == 404:
                self.ready = False  # IN 리소스가 지워졌으면 다음 루프에서 다시 만든다
            raise RuntimeError(f"IN CIN 생성 실패: HTTP {status} {str(body)[:120]}")
        self.last_ri = event["ri"]
        self._save_state()
        self.sent += 1
        LOG.info("IN 기록 #%d: %s", self.sent, con)
        return True

    def run(self, once: bool = False) -> None:
        LOG.info("MN %s%s → IN %s/%s/%s", self.cfg["mn_base"], self.cfg["events_path"],
                 self.cfg["in_base"], self.cfg["in_ae"], self.cfg["in_cnt"])
        error_shown = None
        while True:
            started = time.monotonic()
            try:
                self.step()
                if error_shown:
                    LOG.info("복구됨")
                    error_shown = None
            except (RuntimeError, urllib.error.URLError, OSError, ValueError) as exc:
                msg = str(exc)
                if msg != error_shown:  # 같은 오류는 한 번만 출력
                    LOG.warning("%s (재시도 중)", msg)
                    error_shown = msg
            if once:
                return
            time.sleep(max(0.0, self.cfg["poll_s"] - (time.monotonic() - started)))


def main() -> None:
    ap = argparse.ArgumentParser(description="MN → IN 위험 이벤트 브리지")
    ap.add_argument("--once", action="store_true", help="한 번만 확인하고 종료")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        Bridge(load_config()).run(once=args.once)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
