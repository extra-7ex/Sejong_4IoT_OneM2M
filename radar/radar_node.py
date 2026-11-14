"""LD2450 레이더 업로더: Pi UART로 읽은 표적을 tinyIoT MN의 AE-forklift01/radar에 CIN으로 올린다.

기본은 oneM2M MQTT 바인딩(onem2m/mqtt.md). TRANSPORT=http로 예전 HTTP 방식도 쓸 수 있다.

  python3 radar/radar_node.py                       # MQTT, 같은 Pi의 브로커와 TinyIoT-MN
  TRANSPORT=http python3 radar/radar_node.py        # HTTP
  MQTT_HOST=<브로커 IP> python3 radar/radar_node.py  # 브로커가 다른 기기에 있을 때

필요: pyserial, MQTT일 때 paho-mqtt (`sudo apt install python3-serial python3-paho-mqtt`)
"""
import os, json, math, time, subprocess, threading, queue, itertools
import serial, urllib.request

PI_IP = subprocess.check_output(['hostname', '-I']).split()[0].decode()
TRANSPORT = os.getenv('TRANSPORT', 'mqtt').lower()      # mqtt | http
CSE_NAME = os.getenv('CSE_NAME', 'TinyIoT-MN')          # CSEBase 이름 (docs/cse-naming.md)
CSE_RI = os.getenv('CSE_RI', 'tinyiot-mn')              # CSE_BASE_RI — MQTT 토픽에 쓰임
CSE = os.getenv('CSE_URL', f'http://{PI_IP}:3000/{CSE_NAME}')   # HTTP일 때 주소
MQTT_HOST = os.getenv('MQTT_HOST', '127.0.0.1')
MQTT_PORT = int(os.getenv('MQTT_PORT', '1883'))
SERIAL_PORT = os.getenv('SERIAL_PORT', '/dev/serial0')
ORIGIN = 'Cforklift01'

UPLOAD_INTERVAL = 0.5    # radar 업로드 최소 간격 (초)
LOCAL_DECISION = True    # 위험 판단 엔진 완성 전까지 임시로 alert 직접 기록
WARN_MM = 500            # 경고 거리 (mm)
OFF_DELAY = 1.5          # 이 시간(초) 동안 계속 범위 밖이어야 해제
CON_AS_STRING = True     # tinyIoT는 con에 문자열만 받음
HTTP_TIMEOUT = 5         # (HTTP) tinyIoT 응답 대기 시간

ser = serial.Serial(SERIAL_PORT, 256000, timeout=1)
HEAD, TAIL = b'\xAA\xFF\x03\x00', b'\x55\xCC'

def val(b):  # MSB 1 = 양수, 0 = 음수
    v = int.from_bytes(b, 'little')
    return (v & 0x7FFF) if v & 0x8000 else -(v & 0x7FFF)

if TRANSPORT == 'mqtt':
    from onem2m_mqtt import OneM2MMqtt
    mq = OneM2MMqtt(MQTT_HOST, CSE_NAME, CSE_RI, ORIGIN, port=MQTT_PORT)

def post_cin(path, con):  # tinyIoT 컨테이너에 데이터 한 건 기록
    if TRANSPORT == 'mqtt':
        mq.create_cin(path, con)          # 보내기만 하고 응답은 백그라운드에서 확인 (실패만 출력)
        return
    body = {'m2m:cin': {'con': json.dumps(con) if CON_AS_STRING else con}}
    req = urllib.request.Request(
        f'{CSE}/{path}', method='POST', data=json.dumps(body).encode(),
        headers={'X-M2M-Origin': ORIGIN, 'X-M2M-RI': f'r{time.time_ns()}',
                 'X-M2M-RVI': '3', 'Content-Type': 'application/json;ty=4',
                 'Accept': 'application/json'})
    try:
        urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)
    except Exception as e:
        msg = e.read().decode() if hasattr(e, 'read') else ''
        print(f'!! {path} 업로드 실패: {e} {msg}')

# 업로드 전담 스레드: 메인 루프가 서버 응답을 기다리느라 멈추지 않게 함
q = queue.PriorityQueue()
seq = itertools.count()

def enqueue(path, con, prio):   # prio 0 = alert(우선), 1 = radar
    q.put((prio, next(seq), path, con))

def worker():
    while True:
        _, _, path, con = q.get()
        post_cin(path, con)

threading.Thread(target=worker, daemon=True).start()

def set_alert(level, dist=None):
    print(f'>> alert: {level}' + (f' ({dist}mm)' if dist else ''))
    enqueue('AE-forklift01/alert', {'level': level, 'dist': dist, 'ttc': None}, 0)

if TRANSPORT == 'mqtt':
    print(f'MQTT {MQTT_HOST}:{MQTT_PORT} → {CSE_NAME} (토픽 /oneM2M/req/{ORIGIN}/{CSE_RI}/json)')
else:
    print(f'HTTP → {CSE}')
buf, last_up, level, last_in = bytearray(), 0, 'safe', 0
if LOCAL_DECISION:
    set_alert('safe')                # 시작할 때 안전 상태로 맞춤

while True:
    buf += ser.read(ser.in_waiting or 1)
    i = buf.find(HEAD)
    if i < 0:
        buf = buf[-3:]; continue
    if len(buf) < i + 30:
        continue
    f = bytes(buf[i:i+30]); del buf[:i+30]
    if f[28:30] != TAIL:
        continue

    targets = []
    for n in range(3):
        d = f[4+n*8 : 12+n*8]
        if any(d):                   # 타겟 없으면 전부 0
            targets.append({'slot': n, 'x': val(d[0:2]), 'y': val(d[2:4]), 'v': val(d[4:6])})
    now = time.time()

    # 1) 레이더 데이터: 표적이 있고, 업로드 대기열이 비어 있을 때만 (밀리면 건너뜀)
    if targets and now - last_up >= UPLOAD_INTERVAL and q.empty():
        enqueue('AE-forklift01/radar', {'ts': round(now, 2), 'targets': targets}, 1)
        last_up = now

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
