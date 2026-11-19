"""경보 장치 그룹: 라벨(lbl)로 경보 장치를 찾아 oneM2M 그룹(grp)으로 묶는다. 표준 라이브러리만 쓴다.

    python3 onem2m/alarm_group.py            # 라벨 붙이기 + 경보 장치 찾기 + 그룹 만들기(있으면 다시 만듦)
    python3 onem2m/alarm_group.py --show     # 바꾸지 않고 라벨·그룹·찾은 장치만 보여 줌
    python3 onem2m/alarm_group.py --delete   # 그룹만 지운다 (경보는 다시 각 컨테이너에 직접 써야 함)

하는 일
  1. 라벨: 시연 리소스에 lbl을 붙인다 (예: radar CNT ["safezone:sensor", "sensor:ld2450", "unit:mm"]).
     다른 앱은 이름을 몰라도 `?fu=1&lbl=safezone:alarm`처럼 라벨로 검색해 찾을 수 있다.
  2. 경보 장치 찾기 (oneM2M Discovery)
       - lbl=safezone:alarm 인 컨테이너
       - lbl=type:worker-alarm 인 AE의 alert 컨테이너 (작업자 ESP가 등록할 때 스스로 붙이는 라벨)
  3. 그룹: /TinyIoT-MN/grp-safezone-alarms (mt=3 컨테이너, csy=1 ABANDON_MEMBER)
     경보 작성자가 /grp-safezone-alarms/fopt 에 CIN 하나를 쓰면 MN이 모든 구성원 컨테이너에 같은
     CIN을 만들고(fan-out), 각 장치는 자기 컨테이너 구독으로 알림을 받는다.
     장치를 더 붙여도 작성자 코드는 그대로다. 라벨을 단 장치를 등록하고 이 도구를 다시 돌리면 된다.
  4. 쓰기 권한: 작업자 ESP의 ACP(acp-<노드>)에 경보 작성자(Cforklift01, Criskengine)를 넣는다.
     그룹 fan-out은 작성자 자신의 권한으로 각 구성원에 쓰기 때문이다.

경보 작성자 연결 (/etc/default/safezone)
  기본 모드(레이더 노드가 씀):  RADAR_ALERT_PATH=grp-safezone-alarms/fopt
  엔진 모드:                    ENGINE_ARGS=... --alert-path /grp-safezone-alarms/fopt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Optional

MN = os.getenv("ONEM2M_MN", "http://127.0.0.1:3000/TinyIoT-MN")
ORIGIN = os.getenv("ONEM2M_ADMIN_ORIGIN", "CAdmin")
GROUP_RN = "grp-safezone-alarms"
ALARM_LABEL = "safezone:alarm"
WORKER_AE_LABEL = "type:worker-alarm"
WRITERS = ["Cforklift01", "Criskengine"]     # 경보를 그룹으로 보낼 수 있는 쪽

# 시연 리소스와 붙일 라벨. 없는 리소스는 건너뛴다.
LABELS: dict[str, list[str]] = {
    "/AE-forklift01": ["safezone:forklift", "zone:A"],
    "/AE-forklift01/radar": ["safezone:sensor", "sensor:ld2450", "unit:mm", "zone:A"],
    "/AE-forklift01/alert": [ALARM_LABEL, "alarm:forklift-stop", "zone:A"],
    "/AE-zonealarm01": ["safezone:zonealarm", "zone:A"],
    "/AE-zonealarm01/alert": [ALARM_LABEL, "alarm:zone-light", "zone:A"],
    "/AE-riskengine": ["safezone:mec-app"],
    "/AE-riskengine/events": ["safezone:risk", "zone:A"],
    "/AE-VisionAI": ["safezone:mec-app"],
    "/AE-VisionAI/fusedTracks": ["safezone:vision", "zone:A"],
    "/AE-camera01/detect": ["safezone:vision", "zone:A"],
}
TY_KEY = {2: "m2m:ae", 3: "m2m:cnt", 9: "m2m:grp", 1: "m2m:acp"}

Request = Callable[..., "tuple[int, Any]"]


def http_request(path: str, method: str = "GET", body: Optional[dict] = None, ty: Optional[int] = None,
                 timeout: float = 5) -> tuple[int, Any]:
    headers = {"X-M2M-Origin": ORIGIN, "X-M2M-RI": "grp-" + uuid.uuid4().hex[:10], "X-M2M-RVI": "3",
               "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json" + (f";ty={ty}" if ty else "")
    req = urllib.request.Request(MN + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, json.loads(raw) if raw else None
        except ValueError:
            return exc.code, raw.decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return 0, str(exc)


def to_path(uri: str, base_name: str) -> str:
    """'TinyIoT-MN/AE-x/alert' → '/AE-x/alert' (MN 기준 상대 경로)"""
    return "/" + uri.split("/", 1)[1] if uri.startswith(base_name + "/") else "/" + uri.lstrip("/")


def discover(req: Request, query: str, base_name: str) -> list[str]:
    status, body = req("?fu=1&" + query)
    if status != 200 or not isinstance(body, dict):
        return []
    return sorted(to_path(u, base_name) for u in body.get("m2m:uril", []))


def apply_labels(req: Request, labels: dict[str, list[str]]) -> list[str]:
    """리소스마다 기존 lbl을 지키면서 우리 라벨을 더한다. 바뀐 경로 목록을 돌려준다."""
    changed = []
    for path, want in labels.items():
        status, body = req(path)
        if status != 200 or not isinstance(body, dict) or not body:
            continue
        key, res = next(iter(body.items()))
        have = list(res.get("lbl") or [])
        merged = have + [x for x in want if x not in have]
        if merged == have:
            continue
        status, _ = req(path, "PUT", {key: {"lbl": merged}})
        if status == 200:
            changed.append(path)
        else:
            print(f"  !! {path} 라벨 실패 (HTTP {status})")
    return changed


def find_alarm_members(req: Request, base_name: str) -> list[str]:
    """라벨로 경보 컨테이너를 찾는다: safezone:alarm 컨테이너 + 작업자 AE의 alert."""
    members = set(discover(req, f"ty=3&lbl={ALARM_LABEL}", base_name))
    for ae in discover(req, f"ty=2&lbl={WORKER_AE_LABEL}", base_name):
        status, _ = req(ae + "/alert")
        if status == 200:
            members.add(ae + "/alert")
    return sorted(members)


def grant_writers(req: Request, member: str, writers: list[str]) -> Optional[str]:
    """구성원 컨테이너의 ACP에 작성자가 생성(1)·조회(2) 권한을 갖게 한다. 바꾼 내용을 글로 돌려준다."""
    status, body = req(member)
    if status != 200 or not isinstance(body, dict):
        return None
    cnt = body.get("m2m:cnt", {})
    acpis = cnt.get("acpi") or []
    base_name = MN.rstrip("/").rsplit("/", 1)[-1]
    if not acpis:
        # ACP가 없으면 tinyIoT는 만든 쪽(부모 AE)만 쓰게 한다 → 부모 AE 아래에 작성자용 ACP를 만들어 붙인다
        owner, parent = cnt.get("pi"), member.rsplit("/", 1)[0]
        if not owner or not parent:
            return None
        acp_rn = "acp-alarm-writers"
        status, _ = req(parent, "POST", {"m2m:acp": {
            "rn": acp_rn,
            "pv": {"acr": [{"acor": [owner], "acop": 63}, {"acor": writers, "acop": 3}]},
            "pvs": {"acr": [{"acor": [owner], "acop": 63}]}}}, 1)
        if status not in (201, 409):
            print(f"  !! {parent}/{acp_rn} 만들기 실패 (HTTP {status})")
            return None
        status, _ = req(member, "PUT", {"m2m:cnt": {"acpi": [f"{base_name}{parent}/{acp_rn}"]}})
        if status != 200:
            print(f"  !! {member} ACP 연결 실패 (HTTP {status})")
            return None
        return f"{parent}/{acp_rn}(새로 만듦)에 {', '.join(writers)}"
    changed = None
    for acpi in acpis:
        path = to_path(acpi, base_name)
        status, acp = req(path)
        if status != 200 or not isinstance(acp, dict):
            continue
        acrs = acp["m2m:acp"].get("pv", {}).get("acr", [])
        allowed = {o for r in acrs if (r.get("acop", 0) & 3) == 3 for o in r.get("acor", [])}
        missing = [w for w in writers if w not in allowed and "all" not in allowed]
        if not missing:
            continue
        acrs = acrs + [{"acor": missing, "acop": 3}]
        status, _ = req(path, "PUT", {"m2m:acp": {"pv": {"acr": acrs}}})
        if status == 200:
            changed = f"{path}에 {', '.join(missing)}"
        else:
            print(f"  !! {path} 권한 추가 실패 (HTTP {status})")
    return changed


def build_group(req: Request, members: list[str], base_name: str) -> tuple[int, Any]:
    """그룹을 지우고 다시 만든다(mid를 지금 찾은 구성원으로 맞춤)."""
    req(f"/{GROUP_RN}", "DELETE")
    body = {"m2m:grp": {
        "rn": GROUP_RN, "mt": 3, "mnm": 20, "csy": 1,
        "mid": [base_name + m for m in members],
        "lbl": ["safezone:alarm-group", "zone:A"],
    }}
    return req("", "POST", body, 9)


def show(req: Request, base_name: str) -> None:
    print("라벨로 찾은 리소스")
    for label in ("safezone:sensor", ALARM_LABEL, "safezone:risk", "safezone:vision", "zone:A"):
        found = discover(req, f"lbl={label}", base_name)
        print(f"  lbl={label}: {', '.join(found) if found else '-'}")
    status, body = req(f"/{GROUP_RN}")
    if status != 200 or not isinstance(body, dict):
        print(f"그룹 /{GROUP_RN}: 없음")
        return
    grp = body["m2m:grp"]
    print(f"그룹 /{GROUP_RN}: 구성원 {grp.get('cnm')}개 (mt={grp.get('mt')}, mtv={grp.get('mtv')})")
    # tinyIoT는 mid를 리소스 ID(ri)로 바꿔 저장하므로, 라벨로 찾은 컨테이너의 ri와 맞춰 경로로 보여 준다
    names = {}
    for path in find_alarm_members(req, base_name):
        status, res = req(path)
        if status == 200 and isinstance(res, dict):
            names[res.get("m2m:cnt", {}).get("ri")] = path
    for mid in grp.get("mid", []):
        print(f"  - {names.get(mid, mid + ' (라벨 검색에 없음)')}")


def main(argv: Optional[list[str]] = None, req: Request = http_request) -> int:
    ap = argparse.ArgumentParser(description="SafeZone 경보 장치 그룹 (lbl + grp)")
    ap.add_argument("--show", action="store_true", help="바꾸지 않고 보여 주기만")
    ap.add_argument("--delete", action="store_true", help="그룹을 지운다")
    args = ap.parse_args(argv)
    base_name = MN.rstrip("/").rsplit("/", 1)[-1]

    status, _ = req("")
    if status != 200:
        print(f"MN 응답 없음 ({MN}, HTTP {status})")
        return 1
    if args.show:
        show(req, base_name)
        return 0
    if args.delete:
        status, _ = req(f"/{GROUP_RN}", "DELETE")
        print(f"그룹 삭제: HTTP {status}")
        return 0 if status in (200, 404) else 1

    changed = apply_labels(req, LABELS)
    print(f"1. 라벨: {len(changed)}개 리소스에 붙임" + (f" ({', '.join(changed)})" if changed else " (이미 있음)"))
    members = find_alarm_members(req, base_name)
    if not members:
        print("2. 경보 장치를 찾지 못함 (lbl=safezone:alarm 컨테이너나 type:worker-alarm AE가 없음)")
        return 1
    print(f"2. 라벨 검색으로 찾은 경보 장치 {len(members)}개: {', '.join(members)}")
    granted = [p for p in (grant_writers(req, m, WRITERS) for m in members) if p]
    print("3. 쓰기 권한: " + (", ".join(granted) + " 추가" if granted else "작성자 모두 이미 있음"))
    status, body = build_group(req, members, base_name)
    if status != 201:
        print(f"4. 그룹 만들기 실패: HTTP {status} {body}")
        return 1
    grp = body["m2m:grp"]
    print(f"4. 그룹 /{GROUP_RN}: 구성원 {grp.get('cnm')}개, 같은 종류 확인(mtv)={grp.get('mtv')}")
    print(f"   경보 작성자는 /{GROUP_RN}/fopt 에 CIN 하나를 쓰면 된다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
