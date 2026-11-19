"""시연 전 점검. 표준 라이브러리만 사용한다. Pi에서 저장소 루트 기준으로 실행한다.

    python3 tools/preflight.py          # 점검만 (아무것도 바꾸지 않음)
    python3 tools/preflight.py --fix    # 응답 없는 ESP로 가는 HTTP 구독(SUB)을 지운다

확인하는 것
  1. 서비스: tinyIoT MN·IN, Mosquitto, safezone-* 가 켜져 있는지
  2. 네트워크: Pi IP, tinyIoT SERVER_IP와 일치하는지, ESP에 넣을 CSE 주소
  3. 장치: 레이더 직렬 포트, USB 카메라
  4. 데이터: radar·alert·events·fusedTracks·IPE status 최신 CIN이 얼마나 지났는지
  5. 경보 작성자: 레이더 노드와 엔진 중 하나만 alert를 쓰는지 (/etc/default/safezone),
     그룹(/grp-safezone-alarms/fopt)으로 보내면 그룹과 구성원이 있는지
  6. 구독: HTTP 구독의 ESP가 응답하는지 (nu가 AE-ID면 그 AE의 poa 주소로 확인)

  6이 중요하다. 꺼진 ESP로 가는 HTTP 구독이 남아 있으면 alert CIN을 쓸 때마다 tinyIoT가
  알림 전송에 막혀 약 27초 동안 멈춘다(그동안 다른 요청도 처리하지 못함). --fix로 지우고,
  ESP를 켠 뒤 onem2m/sub_alert_node.sh로 다시 만든다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import socket
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

MN = os.getenv("PREFLIGHT_MN", "http://127.0.0.1:3000/TinyIoT-MN")
IN = os.getenv("PREFLIGHT_IN", "http://127.0.0.1:3001/TinyIoT")
ORIGIN = os.getenv("PREFLIGHT_ORIGIN", "CAdmin")
MN_CONFIG = Path(os.getenv("PREFLIGHT_MN_CONFIG", "/home/user/tinyIoT/source/server/config.h"))
DEFAULTS = Path("/etc/default/safezone")
UNITS = ["tinyiot-mn", "tinyiot-in-local", "mosquitto", "safezone-radar", "safezone-sim-radar",
         "safezone-engine", "safezone-bridge", "safezone-dashboard", "safezone-ipe", "safezone-vision"]
# (경로, 이름, 이 초보다 오래되면 경고. None이면 나이만 보여 줌)
LATEST = [
    ("/AE-forklift01/radar/la", "레이더 radar", 3),
    ("/AE-forklift01/alert/la", "지게차 경보 alert", None),
    ("/AE-riskengine/events/la", "위험 판단 events", None),
    ("/AE-VisionAI/fusedTracks/la", "VisionAI fusedTracks", 3),
    ("/AE-mecIPE/MecServices/safezone-vision/status/la", "IPE 상태", 30),
]

OK, WARN, BAD = "OK ", "주의", "문제"
problems = 0


def say(level: str, text: str) -> None:
    global problems
    if level == BAD:
        problems += 1
    print(f"  [{level}] {text}")


def request(base: str, path: str, method: str = "GET", timeout: float = 3) -> tuple[int, Any]:
    req = urllib.request.Request(base + path, method=method, headers={
        "X-M2M-Origin": ORIGIN, "X-M2M-RI": "pf-" + uuid.uuid4().hex[:10], "X-M2M-RVI": "3",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return 0, None                      # 연결 거부·시간 초과: 응답 없음으로 본다


def con_of(cin: dict) -> Any:
    con = cin.get("con")
    if isinstance(con, str):
        try:
            return json.loads(con)
        except ValueError:
            return con
    return con


def age_s(ct: str) -> Optional[float]:
    try:
        t = dt.datetime.strptime(ct.split(",")[0], "%Y%m%dT%H%M%S").replace(tzinfo=dt.timezone.utc)
    except (ValueError, AttributeError):
        return None
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()


def human(sec: Optional[float]) -> str:
    if sec is None:
        return "?"
    if sec < 90:
        return f"{sec:.0f}초 전"
    if sec < 5400:
        return f"{sec / 60:.0f}분 전"
    return f"{sec / 3600:.1f}시간 전"


def read_defaults() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in DEFAULTS.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = " ".join(shlex.split(value)) if value.strip() else ""
    except OSError:
        pass
    return values


def check_services() -> dict[str, str]:
    print("1. 서비스")
    states = {}
    for unit in UNITS:
        try:
            state = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True,
                                   timeout=5).stdout.strip() or "unknown"
        except (OSError, subprocess.TimeoutExpired):
            state = "unknown"
        states[unit] = state
    for unit in ("tinyiot-mn", "tinyiot-in-local", "mosquitto", "safezone-engine", "safezone-dashboard",
                 "safezone-bridge", "safezone-ipe"):
        say(OK if states[unit] == "active" else BAD, f"{unit}: {states[unit]}")
    radar, sim = states["safezone-radar"], states["safezone-sim-radar"]
    if radar == "active" and sim == "active":
        say(BAD, "실제 레이더와 가상 레이더가 함께 켜져 있음 (하나만)")
    elif radar == "active" or sim == "active":
        say(OK, "레이더: " + ("실제 LD2450 (safezone-radar)" if radar == "active" else "가상 (safezone-sim-radar)"))
    else:
        say(BAD, "레이더 서비스가 꺼져 있음 (safezone-radar 또는 safezone-sim-radar)")
    say(OK if states["safezone-vision"] == "active" else WARN,
        f"safezone-vision: {states['safezone-vision']}" + ("" if states["safezone-vision"] == "active"
                                                          else " (카메라 시연 때 켠다)"))
    return states


def check_network() -> None:
    print("2. 네트워크")
    try:
        ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout.split()
    except (OSError, subprocess.TimeoutExpired):
        ips = []
    lan = [ip for ip in ips if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", ip)
           and not ip.startswith(("100.", "172.17.", "172.18.", "127."))]
    tail = [ip for ip in ips if ip.startswith("100.")]
    say(OK if lan else BAD, "Pi IP: " + (", ".join(lan) if lan else "없음 (Wi-Fi 연결 확인)")
        + (f" · Tailscale {tail[0]}" if tail else ""))
    if lan:
        print(f"         ESP secrets.h에 넣을 CSE 주소: CSE_HOST \"http://{lan[0]}:3000\"")
        print(f"         관제 화면: http://{lan[0]}:8080")
    try:
        text = MN_CONFIG.read_text(encoding="utf-8", errors="replace")
        m = re.search(r'#define\s+SERVER_IP\s+"([^"]+)"', text)
        if m and lan and m.group(1) not in lan:
            say(WARN, f"tinyIoT MN의 SERVER_IP가 {m.group(1)}인데 지금 Pi IP는 {lan[0]} "
                      "(MN 동작에는 지장 없음. 바꾸려면 config.h 수정 후 재빌드)")
        elif m:
            say(OK, f"tinyIoT MN SERVER_IP {m.group(1)}")
    except OSError:
        pass


def check_devices() -> None:
    print("3. 장치")
    say(OK if Path(os.getenv("SERIAL_PORT", "/dev/serial0")).exists() else BAD, "레이더 직렬 포트 /dev/serial0")
    cams = sorted(str(p) for p in Path("/dev").glob("video[0-9]") if p.name in ("video0", "video1", "video2"))
    say(OK if cams else WARN, "USB 카메라: " + (", ".join(cams) if cams else "없음 (카메라 시연 전에 꽂는다)"))


def check_data() -> None:
    print("4. 최신 데이터 (MN)")
    status, _ = request(MN, "")
    if status != 200:
        say(BAD, "MN-CSE 응답 없음" + (f" (HTTP {status})" if status else "") + " → sudo systemctl start tinyiot-mn")
        return
    status, _ = request(IN, "")
    say(OK if status == 200 else BAD, f"IN-CSE {'응답' if status == 200 else '응답 없음'}")
    for path, name, max_age in LATEST:
        status, body = request(MN, path)
        if status != 200 or not body or "m2m:cin" not in body:
            say(WARN if max_age is None or "VisionAI" in name or "IPE" in name else BAD, f"{name}: 데이터 없음")
            continue
        cin = body["m2m:cin"]
        age = age_s(cin.get("ct", ""))
        con = con_of(cin)
        detail = ""
        if isinstance(con, dict):
            if "level" in con:
                detail = f" · level={con.get('level')}"
            elif "status" in con:
                detail = f" · {con.get('status')} ({con.get('reason', '')})"
            elif "state" in con:
                detail = f" · {con.get('state')} ({con.get('reason', '')})"
            elif "targets" in con:
                detail = f" · 표적 {len(con.get('targets') or [])}개" + (" (가상 레이더)" if con.get("src") == "sim" else "")
                ts = con.get("ts")
                if isinstance(ts, (int, float)) and age is not None and age < 10:
                    lag = dt.datetime.now(dt.timezone.utc).timestamp() - ts
                    if lag > 3:
                        say(BAD, f"레이더 값이 측정보다 {lag:.0f}초 늦게 저장됨 → MN 재시작 뒤 밀린 MQTT 메시지가 재생 중일 수 있음. "
                                 "잠시 기다렸다 다시 점검")
        stale = max_age is not None and age is not None and age > max_age
        level = WARN if stale and ("VisionAI" in name or "IPE" in name) else BAD if stale else OK
        say(level, f"{name}: {human(age)}{detail}")


def check_writer(states: dict[str, str]) -> None:
    print("5. 경보 작성자 (alert는 하나만 쓴다)")
    env = read_defaults()
    radar_local = env.get("RADAR_LOCAL_DECISION", "1") != "0"
    engine_alert = "--alert-path" in env.get("ENGINE_ARGS", "")
    sim = states.get("safezone-sim-radar") == "active"
    if engine_alert and radar_local and not sim:
        say(BAD, "레이더 노드와 엔진이 둘 다 alert를 씀 → /etc/default/safezone에 RADAR_LOCAL_DECISION=0")
    elif not engine_alert and (not radar_local or sim):
        say(BAD, "아무도 alert를 쓰지 않음 → 지게차가 반응하지 않음 (가상 레이더는 엔진 모드로만 경보가 감)")
    elif engine_alert:
        say(OK, "엔진 모드: 위험 엔진이 alert를 씀 (카메라 결합 판단이 지게차까지 감)")
    else:
        say(OK, "기본 모드: 레이더 노드가 거리로 alert를 씀 (카메라 결합은 관제 화면에만)")
    m = re.search(r"--alert-path\s+(\S+)", env.get("ENGINE_ARGS", ""))
    target = (m.group(1) if engine_alert and m else "/" + env.get("RADAR_ALERT_PATH", "AE-forklift01/alert").strip("/"))
    if "/fopt" not in target:
        say(OK, f"alert 경로: {target}")
        return
    group = target.split("/fopt")[0]
    status, body = request(MN, group)
    grp = (body or {}).get("m2m:grp", {}) if status == 200 else {}
    if not grp:
        say(BAD, f"alert를 그룹 {group}/fopt로 보내는데 그룹이 없음 → python3 onem2m/alarm_group.py")
    elif not grp.get("cnm"):
        say(BAD, f"그룹 {group}에 구성원이 없음 → python3 onem2m/alarm_group.py")
    else:
        say(OK, f"alert 경로: 그룹 {group}/fopt → 경보 장치 {grp.get('cnm')}곳에 한 번에 (fan-out)")


def http_target(nu: str) -> Optional[tuple[str, int]]:
    if not nu.startswith(("http://", "https://")):
        return None
    u = urllib.parse.urlparse(nu)
    return u.hostname or "", u.port or (443 if u.scheme == "https" else 80)


def reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def ae_poas(base_name: str) -> dict[str, list[str]]:
    """AE-ID(aei) → poa 목록. 작업자 ESP는 구독 nu에 자기 AE-ID를 넣으므로 실제 주소는 poa에 있다."""
    out: dict[str, list[str]] = {}
    status, body = request(MN, "?fu=1&ty=2")
    for uri in (body or {}).get("m2m:uril", []) if status == 200 else []:
        path = "/" + uri.split("/", 1)[1] if uri.startswith(base_name + "/") else "/" + uri
        status, ae = request(MN, path)
        ae = (ae or {}).get("m2m:ae", {}) if status == 200 else {}
        if ae.get("aei"):
            out[ae["aei"]] = ae.get("poa") or []
    return out


def check_subscriptions(fix: bool) -> None:
    print("6. 구독 (꺼진 ESP로 가는 HTTP 구독은 MN을 약 27초씩 멈추게 한다)")
    status, body = request(MN, "?fu=1&ty=23")
    if status != 200 or not body:
        say(WARN, "구독 목록을 읽지 못함")
        return
    base_name = MN.rstrip("/").rsplit("/", 1)[-1]
    http_subs = 0
    poa_of: Optional[dict[str, list[str]]] = None
    for uri in body.get("m2m:uril", []):
        path = "/" + uri.split("/", 1)[1] if uri.startswith(base_name + "/") else "/" + uri
        status, sub = request(MN, path)
        if status != 200 or not sub:
            continue
        for nu in sub.get("m2m:sub", {}).get("nu", []):
            target, shown = http_target(nu), nu
            if target is None and "/" not in nu and ":" not in nu:
                # nu가 AE-ID(예: Cworker01)면 알림은 그 AE의 poa로 간다 → poa 주소를 확인한다
                if poa_of is None:
                    poa_of = ae_poas(base_name)
                poas = [p for p in poa_of.get(nu, []) if http_target(p)]
                if not poas:
                    continue
                target, shown = http_target(poas[0]), f"{nu} (poa {poas[0]})"
            if target is None:
                continue
            http_subs += 1
            if reachable(*target):
                say(OK, f"{path} → {shown} 응답함")
            elif fix:
                status, _ = request(MN, path, "DELETE")
                say(OK if status in (200, 202, 204) else BAD, f"{path} → {shown} 응답 없음 → 삭제 (HTTP {status})")
            else:
                say(BAD, f"{path} → {shown} 응답 없음 (--fix로 삭제하고 ESP를 켠 뒤 다시 구독)")
    status, alert_children = request(MN, "/AE-forklift01/alert?fu=1&ty=23")
    subs = (alert_children or {}).get("m2m:uril", []) if status == 200 else []
    if not subs:
        say(WARN, "지게차 alert에 구독이 없음 → ESP를 켜고 'bash onem2m/sub_alert_node.sh <ESP IP>'")
    if http_subs == 0:
        say(WARN, "HTTP 구독이 하나도 없음 (ESP 연결 전이면 정상)")


def main() -> None:
    ap = argparse.ArgumentParser(description="SafeZone 시연 전 점검")
    ap.add_argument("--fix", action="store_true", help="응답 없는 HTTP 구독을 지운다")
    args = ap.parse_args()
    print("SafeZone 시연 전 점검  " + dt.datetime.now().strftime("%m/%d %H:%M:%S"))
    states = check_services()
    check_network()
    check_devices()
    check_data()
    check_writer(states)
    check_subscriptions(args.fix)
    print()
    print("문제 없음" if problems == 0 else f"문제 {problems}개: 위의 [문제] 줄을 먼저 해결한다")


if __name__ == "__main__":
    main()
