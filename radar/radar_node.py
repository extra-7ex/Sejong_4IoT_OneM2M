"""레이더 노드: LD2450(/dev/serial0) → tinyIoT AE-forklift01/radar

radar CIN의 con (JSON 문자열):
  표적 있음: {"ts": 1762826978.12, "targets": [{"slot": 0, "x": 373, "y": 366, "v": -8}]}
  표적 없음: {"ts": 1762826978.12, "targets": []}
  - ts   : Pi가 프레임을 시리얼에서 다 받아 해석한 시각 (Pi 시스템 시각, 초)
           센서 측정 시각도, tinyIoT CIN 생성 시각(ct)도 아님
  - slot : LD2450 프레임 안 표적 자리 번호(0~2), 빈 자리가 있어도 번호를 당기지 않음
  - x, y : mm / v : cm/s
  - UPLOAD_INTERVAL마다 전송 시도, 이전 요청이 대기열에 남아 있으면 건너뜀
  - 레이더/시리얼이 멈추면 프레임이 없으므로 아무것도 보내지 않음 (빈 프레임과 구분됨)
"""
import os, json, math, time, subprocess, threading, queue, itertools
import serial, urllib.request

PI_IP = subprocess.check_output(['hostname', '-I']).split()[0].decode()
CSE = os.getenv('CSE_URL', f'http://{PI_IP}:3000/TinyIoT')   # tinyIoT 주소 (자동)
ORIGIN = 'Cforklift01'

UPLOAD_INTERVAL = 0.5    # radar 업로드 간격(초): 표적 유무와 관계없이 이 간격으로 전송 시도
LOCAL_DECISION = True    # 위험 판단 엔진 완성 전까지 임시로 alert 직접 기록
WARN_MM = 500            # 경고 거리 (mm)
OFF_DELAY = 1.5          # 이 시간(초) 동안 계속 범위 밖이어야 해제
CON_AS_STRING = True     # tinyIoT는 con에 문자열만 받음
HTTP_TIMEOUT = 5         # tinyIoT 응답이 약 2초 걸려서 넉넉하게
LOG_UPLOAD = True        # 업로드 응답 시간·간격, 프레임 공백 출력 (진단용)

ser = serial.Serial('/dev/serial0', 256000, timeout=1)
HEAD, TAIL = b'\xAA\xFF\x03\x00', b'\x55\xCC'

def val(b):  # MSB 1 = 양수, 0 = 음수
    v = int.from_bytes(b, 'little')
    return (v & 0x7FFF) if v & 0x8000 else -(v & 0x7FFF)

def post_cin(path, con):  # tinyIoT 컨테이너에 데이터 한 건 기록, 성공하면 True
    body = {'m2m:cin': {'con': json.dumps(con) if CON_AS_STRING else con}}
    req = urllib.request.Request(
        f'{CSE}/{path}', method='POST', data=json.dumps(body).encode(),
        headers={'X-M2M-Origin': ORIGIN, 'X-M2M-RI': f'r{time.time_ns()}',
                 'X-M2M-RVI': '3', 'Content-Type': 'application/json;ty=4',
                 'Accept': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
        return True
    except Exception as e:
        msg = e.read().decode() if hasattr(e, 'read') else ''
        print(f'!! {path} 업로드 실패: {e} {msg}')
        return False

# 업로드 전담 스레드: 메인 루프가 서버 응답을 기다리느라 멈추지 않게 함
q = queue.PriorityQueue()
seq = itertools.count()

def enqueue(path, con, prio):   # prio 0 = alert(우선), 1 = radar
    q.put((prio, next(seq), path, con))

def worker():
    last = None                  # 직전 radar 업로드 시작 시각
    while True:
        _, _, path, con = q.get()
        t0 = time.time()
        ok = post_cin(path, con)
        if LOG_UPLOAD and path.endswith('/radar'):
            gap = f'{t0 - last:.2f}s' if last is not None else '-'
            print(f'radar: 표적 {len(con["targets"])}개, 응답 {time.time() - t0:.2f}s, '
                  f'간격 {gap}' + ('' if ok else ' (실패)'))
            last = t0
        elif LOG_UPLOAD:
            print(f'alert: 응답 {time.time() - t0:.2f}s' + ('' if ok else ' (실패)'))

threading.Thread(target=worker, daemon=True).start()

def set_alert(level, dist=None):
    print(f'>> alert: {level}' + (f' ({dist}mm)' if dist else ''))
    enqueue('AE-forklift01/alert', {'level': level, 'dist': dist, 'ttc': None}, 0)

print(f'CSE: {CSE}  (radar {UPLOAD_INTERVAL}s 간격, 빈 프레임 포함)')
buf, last_up, level, last_in, last_slots = bytearray(), 0, 'safe', 0, []
if LOCAL_DECISION:
    set_alert('safe')                # 시작할 때 안전 상태로 맞춤
last_frame, nbytes, bad = time.time(), 0, 0   # 프레임 공백 진단용

while True:
    chunk = ser.read(ser.in_waiting or 1)
    buf += chunk; nbytes += len(chunk)
    i = buf.find(HEAD)
    if i < 0:
        buf = buf[-3:]; continue
    if len(buf) < i + 30:
        continue
    f = bytes(buf[i:i+30]); del buf[:i+30]
    if f[28:30] != TAIL:
        bad += 1; continue
    t_frame = time.time()
    if LOG_UPLOAD and t_frame - last_frame > 0.3:   # 0.3초 넘게 정상 프레임이 없었으면 출력
        print(f'프레임 공백 {t_frame - last_frame:.2f}s: 그동안 받은 바이트 {nbytes}, 깨진 프레임 {bad}')
    last_frame, nbytes, bad = t_frame, 0, 0

    targets = []
    for n in range(3):
        d = f[4+n*8 : 12+n*8]
        if any(d):                   # 빈 슬롯은 전부 0
            targets.append({'slot': n, 'x': val(d[0:2]), 'y': val(d[2:4]), 'v': val(d[4:6])})
    now = time.time()                # ts: Pi가 이 프레임을 시리얼에서 다 받아 해석한 시각

    # 1) 레이더 데이터: 표적이 없어도(targets: []) UPLOAD_INTERVAL마다 전송 시도
    #    이전 요청이 대기열에 남아 있으면 이번 프레임은 건너뜀
    if now - last_up >= UPLOAD_INTERVAL and q.empty():
        enqueue('AE-forklift01/radar', {'ts': round(now, 2), 'targets': targets}, 1)
        last_up = now

    # 슬롯 유지 여부 실측용: 차 있는 슬롯 구성이 바뀔 때만 출력
    slots = [t['slot'] for t in targets]
    if slots != last_slots:
        print(f'슬롯 변화: {last_slots} → {slots}')
        last_slots = slots

    # 2) 임시 위험 판단 (proximity.py와 같은 로직, 결과를 alert에 기록)
    if not LOCAL_DECISION:
        continue
    near = min((math.hypot(t['x'], t['y']) for t in targets), default=None)
    if near is not None and near <= WARN_MM:
        last_in = now
        if level != 'danger':        # 안전 → 위험 바뀔 때만 기록
            level = 'danger'; set_alert('danger', round(near))
    elif level == 'danger' and now - last_in >= OFF_DELAY:
        level = 'safe'; set_alert('safe')
