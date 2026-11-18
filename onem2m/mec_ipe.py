"""MEC 서비스 생존 확인 IPE. 표준 라이브러리만 사용한다.

사용한 MEC platform 구현(AdvantEDGE)은 MEC 011의 liveness를 처리하지 않아서,
서비스 프로세스가 죽어도 레지스트리에는 ACTIVE로 남는다. 이 IPE가 서비스를 직접
확인해서 그 결과를 MN-CSE에 oneM2M 리소스로 기록한다.

확인 방법 (IPE_PROBE)
    cin:<경로>   그 서비스가 MN-CSE에 쓰는 최신 CIN이 신선한지 본다 (기본: VisionAI fusedTracks).
                 ts가 IPE_MAX_AGE_S 안이고 cam_ok가 false가 아니면 성공.
    http(s)://…  그 주소에 GET을 보내 2xx면 성공.

판정
    IPE_PERIOD_S마다 확인한다. IPE_FAIL_N번 연속 실패하면 INACTIVE, 한 번 성공하면 ACTIVE.
    기본값(1초, 3번, 2초)이면 서비스가 멈추고 약 4–5초 뒤 INACTIVE가 된다.
    MN-CSE에 연결할 수 없을 때는 서비스 탓이 아니므로 실패로 세지 않는다.

기록 (MN-CSE)
    AE-mecIPE/MecServices/<서비스>/status 에 상태가 바뀔 때마다, 그리고 IPE_HEARTBEAT_S마다 CIN을 쓴다.
    con 예: {"service":"safezone-vision","state":"INACTIVE","reason":"stale 3.2s","fails":3,
             "since":1795000000.12,"ts":1795000004.5,"probe":"cin","registry_state":"ACTIVE"}
    읽는 쪽은 status/la의 ts가 30초 넘게 지났으면 IPE가 멈춘 것으로 보고 UNKNOWN으로 다룬다.

MEC 레지스트리 (선택)
    IPE_MEC_BASE에 MEC 011 서비스 관리 API 주소를 주면 레지스트리 상태도 함께 기록한다.
    IPE_MEC_UPDATE=1이면 판정이 레지스트리와 다를 때 서비스 상태를 PUT으로 바꿔서,
    MEC 쪽 구독자도 SerAvailabilityNotification을 받게 한다.

실행 (저장소 루트에서):
    python3 -m onem2m.mec_ipe
    python3 -m onem2m.mec_ipe --once     # 한 번만 확인하고 기록 후 종료 (시험용)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional

from onem2m.mn_to_in_bridge import Cse, latest_cin

LOG = logging.getLogger("mec-ipe")
ACTIVE, INACTIVE = "ACTIVE", "INACTIVE"
NET_ERRORS = (urllib.error.URLError, OSError, ValueError)


def load_config() -> dict[str, Any]:
    env = os.getenv
    return {
        "mn_base": env("IPE_MN_BASE", "http://127.0.0.1:3000/TinyIoT-MN").rstrip("/"),
        "read_origin": env("IPE_READ_ORIGIN", "CAdmin"),     # 다른 AE의 CIN 조회용 (ACP가 없으면 소유자만 읽음)
        "origin": env("IPE_ORIGIN", "CmecIPE"),              # 자기 AE 생성·기록용
        "ae": env("IPE_AE", "AE-mecIPE"),
        "service": env("IPE_SERVICE", "safezone-vision"),
        "probe": env("IPE_PROBE", "cin:/AE-VisionAI/fusedTracks/la"),
        "period_s": float(env("IPE_PERIOD_S", "1.0")),
        "fail_n": int(env("IPE_FAIL_N", "3")),
        "max_age_s": float(env("IPE_MAX_AGE_S", "2.0")),
        "heartbeat_s": float(env("IPE_HEARTBEAT_S", "10")),
        "status_mni": int(env("IPE_STATUS_MNI", "100")),
        "mec_base": env("IPE_MEC_BASE", "").rstrip("/"),   # 예: http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1
        "mec_service": env("IPE_MEC_SERVICE", ""),          # 레지스트리의 serName (비우면 service와 같음)
        "mec_update": env("IPE_MEC_UPDATE", "0") == "1",
        "rvi": env("IPE_RVI", "3"),
        "timeout_s": float(env("IPE_TIMEOUT_S", "5")),
    }


# ---------------------------------------------------------------- 확인(probe)

def check_cin(cse: Cse, path: str, max_age_s: float, now: float) -> tuple[bool, str]:
    """서비스가 쓰는 최신 CIN이 신선하면 (True, 'fresh'). MN 연결 오류는 예외로 올린다."""
    cin = latest_cin(cse, path)
    if cin is None:
        return False, "no_cin"
    con = cin["con"]
    ts = con.get("ts") if isinstance(con, dict) else None
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        return False, "no_ts"
    age = now - float(ts)
    if age > max_age_s:
        return False, f"stale {age:.1f}s"
    if age < -max_age_s:
        return False, "clock_skew"
    if con.get("cam_ok") is False:
        return False, "cam_fail"
    return True, "fresh"


def check_http(url: str, timeout_s: float) -> tuple[bool, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as res:
            return 200 <= res.status < 300, f"http {res.status}"
    except urllib.error.HTTPError as exc:
        return False, f"http {exc.code}"
    except NET_ERRORS as exc:
        return False, f"unreachable {type(exc).__name__}"


# ---------------------------------------------------------------- 판정

class Liveness:
    """연속 실패 fail_n번이면 INACTIVE, 성공 한 번이면 ACTIVE. 상태가 바뀌면 observe가 True."""

    def __init__(self, fail_n: int):
        self.fail_n = max(1, fail_n)
        self.state: Optional[str] = None   # 첫 판정 전
        self.fails = 0
        self.reason = ""
        self.since: Optional[float] = None

    def observe(self, ok: bool, reason: str, now: float) -> bool:
        self.reason = reason
        if ok:
            self.fails = 0
            new = ACTIVE
        else:
            self.fails += 1
            new = INACTIVE if self.fails >= self.fail_n else self.state
        if new is not None and new != self.state:
            self.state, self.since = new, now
            return True
        return False


# ---------------------------------------------------------------- MEC 011 레지스트리

def _http_json(url: str, method: str = "GET", body: Any = None, timeout_s: float = 5) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Accept": "application/json", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as res:
        raw = res.read()
        return json.loads(raw) if raw else None


class MecRegistry:
    def __init__(self, base: str, ser_name: str, timeout_s: float, http: Callable[..., Any] = _http_json):
        self.base, self.ser_name, self.timeout_s, self.http = base, ser_name, timeout_s, http

    def entry(self) -> Optional[dict]:
        query = urllib.parse.urlencode({"ser_name": self.ser_name})
        entries = self.http(f"{self.base}/services?{query}", timeout_s=self.timeout_s)
        if not isinstance(entries, list) or len(entries) != 1:
            return None
        return entries[0]

    def set_state(self, entry: dict, state: str) -> None:
        url = entry["_links"]["self"]["href"]
        self.http(url, "PUT", dict(entry, state=state), timeout_s=self.timeout_s)


# ---------------------------------------------------------------- IPE

class Ipe:
    def __init__(self, cfg: dict[str, Any], reader: Optional[Cse] = None, writer: Optional[Cse] = None,
                 registry: Optional[MecRegistry] = None, clock: Callable[[], float] = time.time):
        self.cfg = cfg
        self.reader = reader or Cse(cfg["mn_base"], cfg["read_origin"], cfg["rvi"], cfg["timeout_s"])
        self.writer = writer or Cse(cfg["mn_base"], cfg["origin"], cfg["rvi"], cfg["timeout_s"])
        if registry is None and cfg["mec_base"]:
            registry = MecRegistry(cfg["mec_base"], cfg["mec_service"] or cfg["service"], cfg["timeout_s"])
        self.registry = registry
        self.clock = clock
        self.live = Liveness(cfg["fail_n"])
        self.status_path = f"/{cfg['ae']}/MecServices/{cfg['service']}/status"
        self.ready = False
        self.last_write: Optional[float] = None
        self.pending = False          # 기록해야 하는데 아직 못 쓴 상태 변화
        self.written = 0

    # oneM2M 리소스 -------------------------------------------------------
    def _ensure(self, path: str, ty: int, body: dict) -> None:
        status, _ = self.writer.request("GET", path)
        if 200 <= status < 300:
            return
        if status != 404:
            raise RuntimeError(f"GET {path} → HTTP {status} (originator {self.cfg['origin']} 권한 확인)")
        parent = path.rsplit("/", 1)[0]
        status, resp = self.writer.request("POST", parent, ty, body)
        if status not in (200, 201, 409):
            raise RuntimeError(f"{path} 생성 실패: HTTP {status} {str(resp)[:120]}")
        LOG.info("MN에 %s 생성", path)

    def ensure_resources(self) -> None:
        ae = f"/{self.cfg['ae']}"
        self._ensure(ae, 2, {"m2m:ae": {"rn": self.cfg["ae"], "api": "NmecIPE", "rr": True, "srv": ["3"]}})
        self._ensure(f"{ae}/MecServices", 3, {"m2m:cnt": {"rn": "MecServices"}})
        self._ensure(f"{ae}/MecServices/{self.cfg['service']}", 3, {"m2m:cnt": {"rn": self.cfg["service"]}})
        self._ensure(self.status_path, 3, {"m2m:cnt": {"rn": "status", "mni": self.cfg["status_mni"]}})
        self.ready = True

    # 한 번 확인 ----------------------------------------------------------
    def probe(self, now: float) -> tuple[Optional[bool], str]:
        """(성공 여부, 사유). MN에 연결하지 못해 판단할 수 없으면 (None, 사유)."""
        target = self.cfg["probe"]
        if target.startswith("cin:"):
            try:
                return check_cin(self.reader, target[4:], self.cfg["max_age_s"], now)
            except (RuntimeError, *NET_ERRORS) as exc:
                return None, f"mn_error {str(exc)[:80]}"
        return check_http(target, self.cfg["timeout_s"])

    def registry_state(self) -> Optional[str]:
        if self.registry is None:
            return None
        try:
            entry = self.registry.entry()
            if entry is None:
                return "not_registered"
            state = entry.get("state")
            if self.cfg["mec_update"] and self.live.state in (ACTIVE, INACTIVE) and state != self.live.state:
                self.registry.set_state(entry, self.live.state)
                LOG.info("MEC 레지스트리 %s: %s → %s", self.registry.ser_name, state, self.live.state)
                state = self.live.state
            return state
        except (KeyError, TypeError, *NET_ERRORS) as exc:
            LOG.warning("MEC 레지스트리 확인 실패: %s", exc)
            return "error"

    def status_con(self, now: float, registry_state: Optional[str]) -> dict:
        con = {"service": self.cfg["service"], "state": self.live.state, "reason": self.live.reason[:60],
               "fails": self.live.fails, "since": round(self.live.since or now, 2), "ts": round(now, 2),
               "probe": "cin" if self.cfg["probe"].startswith("cin:") else "http"}
        if registry_state is not None:
            con["registry_state"] = registry_state
        return con

    def write(self, con: dict) -> None:
        status, body = self.writer.request("POST", self.status_path, 4,
                                           {"m2m:cin": {"con": json.dumps(con, separators=(",", ":"))}})
        if status not in (200, 201):
            if status == 404:
                self.ready = False   # 리소스가 지워졌으면 다음에 다시 만든다
            raise RuntimeError(f"status CIN 생성 실패: HTTP {status} {str(body)[:120]}")
        self.written += 1

    def step(self) -> Optional[dict]:
        """한 번 확인하고, 기록했으면 그 con을 돌려준다."""
        now = self.clock()
        ok, reason = self.probe(now)
        if ok is None:
            LOG.warning("확인 보류: %s", reason)
        else:
            before = self.live.state
            if self.live.observe(ok, reason, now):
                LOG.info("%s: %s → %s (%s)", self.cfg["service"], before or "시작", self.live.state, reason)
                self.pending = True
        if self.live.state is None:
            return None
        due = self.last_write is None or now - self.last_write >= self.cfg["heartbeat_s"]
        if not (self.pending or due):
            return None
        if not self.ready:
            self.ensure_resources()
        con = self.status_con(now, self.registry_state())
        self.write(con)
        self.pending, self.last_write = False, now
        return con

    def run(self, once: bool = False) -> None:
        LOG.info("%s 확인: %s → MN %s%s", self.cfg["service"], self.cfg["probe"], self.cfg["mn_base"], self.status_path)
        error_shown = None
        while True:
            started = time.monotonic()
            try:
                self.step()
                if error_shown:
                    LOG.info("기록 복구됨")
                    error_shown = None
            except (RuntimeError, *NET_ERRORS) as exc:
                msg = str(exc)
                if msg != error_shown:
                    LOG.warning("%s (재시도 중)", msg)
                    error_shown = msg
            if once:
                return
            time.sleep(max(0.0, self.cfg["period_s"] - (time.monotonic() - started)))


def main() -> None:
    ap = argparse.ArgumentParser(description="MEC 서비스 생존 확인 IPE")
    ap.add_argument("--once", action="store_true", help="한 번만 확인하고 기록 후 종료")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        Ipe(load_config()).run(once=args.once)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
