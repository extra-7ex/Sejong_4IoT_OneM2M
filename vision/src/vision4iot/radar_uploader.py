"""레이더 업로더: 레이더 입력 → 팀 형식 CIN → tinyIoT `AE-forklift01/radar` (CLAUDE.md 13장).

팀 깃허브에 레이더 값을 tinyIoT에 올리는 프로그램이 없어서(2장 빈 연결 1) 우리가 채운다. 팀 코드는 고치지 않는다.
- 지금은 sim만. 장비(LD2450)가 오면 serial로 바꾼다.
- 표적이 없어도 매번 `targets: []`를 올린다 — 엔진은 새 CIN이 1초 넘게 없으면 UNKNOWN이 된다.
- sim 데이터는 con에 `"src": "sim"`을 넣고 로그에 [SIM]으로 찍는다. 데모에서 실제 레이더처럼 보여 주지 않는다.
- AE·CNT는 만들지 않는다(팀 `setup_onem2m.sh` 몫). 404면 그 스크립트를 먼저 돌리라고 알려 준다.

  python -m vision4iot.radar_uploader --base-url http://127.0.0.1:3000        # Pi에서, 시험용 CSE로
  python -m vision4iot.radar_uploader --dry-run                               # CSE 없이 con만 1초마다 출력
"""
import argparse
import json
import sys
import time

from vision4iot.config import load_config, resolve
from vision4iot.onem2m import Client
from vision4iot.radar.base import to_team_con
from vision4iot.radar.sim import RadarSim


def make_source(rcfg, sim_mode=None):
    if rcfg["source"] == "sim":
        mode = sim_mode or rcfg.get("uploader", {}).get("sim_mode", "script")
        if mode == "from_camera":
            raise SystemExit("업로더는 카메라 없이 돈다 → --mode script 또는 ghost (from_camera는 융합 단계용)")
        return RadarSim.from_cfg({**rcfg["sim"], "mode": mode}, resolve), "sim"
    raise SystemExit(f"radar.source={rcfg['source']!r}: 업로더는 아직 sim만 지원 (serial은 LD2450이 오면, CLAUDE.md 14장)")


def summary(con, tag):
    ts = con["targets"]
    near = min((t["x"] ** 2 + t["y"] ** 2) ** 0.5 for t in ts) / 1000 if ts else None
    return f"[{tag.upper()}] targets {len(ts)}" + (f" nearest {near:.2f} m" if near is not None else "")


def run(source, tag, send, hz=10.0, flip_x=False, flip_v=False, duration=None,
        clock=time.time, sleep=time.sleep, log=print):
    """hz로 표적을 만들어 send(con)를 부른다. send는 (ok, 메시지)를 돌려준다. 1초마다 요약 한 줄.
    duration(s)을 주면 그만큼만 돈다(시험용). 보낸 횟수·성공 횟수를 돌려준다."""
    period = 1.0 / hz
    start = next_t = clock()
    sent = ok_n = 0
    win_ok = win_n = 0
    last_log, last_err = start, None
    while duration is None or clock() - start < duration:
        ts = clock()
        con = to_team_con(source.get_targets(ts), ts, flip_x, flip_v, src=tag)
        ok, msg = send(con)
        sent += 1
        win_n += 1
        if ok:
            ok_n += 1
            win_ok += 1
        else:
            last_err = msg
        if ts - last_log >= 1.0:
            line = f"{summary(con, tag)} | sent {win_ok}/{win_n}"
            if win_ok < win_n and last_err:
                line += f" | ERROR {last_err}"
            log(line)
            last_log, win_ok, win_n, last_err = ts, 0, 0, None
        next_t += period
        delay = next_t - clock()
        if delay > 0:
            sleep(delay)
        else:
            next_t = clock()          # 밀렸으면 따라잡으려 몰아 보내지 않는다
    return sent, ok_n


def http_sender(client, path):
    hinted = False

    def send(con):
        nonlocal hinted
        try:
            status, body = client.post_cin(path, con)
        except OSError as e:
            return False, f"CSE 연결 안 됨 ({client.url()}): {e}"
        if status in (200, 201):
            return True, None
        msg = f"HTTP {status} {json.dumps(body, ensure_ascii=False)[:120] if body else ''}"
        if status == 404 and not hinted:
            hinted = True
            msg += " — 컨테이너가 없음: 팀 onem2m/setup_onem2m.sh를 먼저 실행"
        return False, msg
    return send


def main(argv=None):
    ap = argparse.ArgumentParser(description="레이더(sim) → tinyIoT AE-forklift01/radar")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--base-url", help="CSE 주소, 예 http://127.0.0.1:3000 (config onem2m.base_url 대신)")
    ap.add_argument("--hz", type=float, help="초당 올리는 횟수 (config radar.uploader.hz 대신)")
    ap.add_argument("--duration", type=float, help="이 시간(s)만 돌고 끝 (기본: Ctrl+C까지)")
    ap.add_argument("--mode", choices=["script", "ghost"], help="sim 모드 (config radar.uploader.sim_mode 대신)")
    ap.add_argument("--dry-run", action="store_true", help="CSE에 보내지 않고 con을 1초마다 출력")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    rcfg, ocfg = cfg["radar"], cfg["onem2m"]
    ucfg = rcfg.get("uploader", {})
    source, tag = make_source(rcfg, args.mode)
    hz = args.hz or ucfg.get("hz", 10)
    path = ocfg["radar_path"]

    if args.dry_run:
        last = [0.0]

        def send(con):
            if con["ts"] - last[0] >= 1.0:
                print(json.dumps(con), flush=True)
                last[0] = con["ts"]
            return True, None
        where = "dry-run (보내지 않음)"
    else:
        base = args.base_url or ocfg.get("base_url")
        if not base:
            print("ERROR: CSE 주소가 없음 — --base-url http://<Pi IP>:3000 또는 config.local.yaml의 onem2m.base_url",
                  file=sys.stderr)
            return 2
        client = Client(base, ocfg["cse_name"], ucfg.get("originator", "Cforklift01"))
        send = http_sender(client, path)
        where = client.url(path)

    scen = f" scenario={source.scenario_name}" if tag == "sim" else ""
    print(f"radar uploader: source={tag} mode={getattr(source, 'mode', '-')}{scen} {hz:g} Hz → {where}", flush=True)
    if tag == "sim":
        print("  ※ 시뮬레이터 데이터입니다 (con.src = \"sim\"). 실제 레이더가 아닙니다.", flush=True)
    try:
        sent, ok = run(source, tag, send, hz, rcfg.get("flip_x", False), rcfg.get("flip_v", False), args.duration,
                       log=lambda s: print(s, flush=True))
    except KeyboardInterrupt:
        return 0
    print(f"done: {ok}/{sent} sent", flush=True)
    return 0 if ok == sent else 1


if __name__ == "__main__":
    sys.exit(main())
