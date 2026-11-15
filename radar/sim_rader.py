#!/usr/bin/env python3
"""가상 레이더: radar_node.py와 같은 형식으로 AE-forklift01/radar에 10Hz 업로드 (레이더 없이 엔진 시험용)

기본은 MQTT. TRANSPORT=http로 예전 방식. 주소·이름은 radar_node.py와 같은 환경 변수를 쓴다.
"""
import json, math, os, subprocess, time, urllib.request

PI_IP = subprocess.check_output(['hostname', '-I']).split()[0].decode()
TRANSPORT = os.getenv('TRANSPORT', 'mqtt').lower()
CSE_NAME = os.getenv('CSE_NAME', 'TinyIoT-MN')
CSE_RI = os.getenv('CSE_RI', 'tinyiot-mn')
CSE = os.getenv('CSE_URL', f'http://{PI_IP}:3000/{CSE_NAME}')
MQTT_HOST = os.getenv('MQTT_HOST', '127.0.0.1')
HZ = 10

if TRANSPORT == 'mqtt':
    from onem2m_mqtt import OneM2MMqtt
    mq = OneM2MMqtt(MQTT_HOST, CSE_NAME, CSE_RI, 'Cforklift01')

def post(con):
    if TRANSPORT == 'mqtt':
        mq.create_cin('AE-forklift01/radar', con)
        return
    body = json.dumps({'m2m:cin': {'con': json.dumps(con)}}).encode()
    req = urllib.request.Request(f'{CSE}/AE-forklift01/radar', data=body, method='POST', headers={
        'X-M2M-Origin': 'Cforklift01', 'X-M2M-RI': f's{time.time_ns()}', 'X-M2M-RVI': '3',
        'Content-Type': 'application/json;ty=4', 'Accept': 'application/json'})
    urllib.request.urlopen(req, timeout=5)

def scene(t):                                      # 30초 시나리오 반복
    t %= 30
    if t < 3:    return None                       # 아무도 없음
    if t < 11:   y, v = 5000 - (t - 3) * 525, -52  # 5m → 0.8m 접근
    elif t < 14: y, v = 800, 0                     # 0.8m에서 정지
    elif t < 20: y, v = 800 + (t - 14) * 700, 70   # 멀어짐
    else:        return None                       # 다시 아무도 없음
    return {'slot': 0, 'x': 200, 'y': round(y), 'v': v}

dest = f'MQTT {MQTT_HOST} → {CSE_NAME}' if TRANSPORT == 'mqtt' else CSE
print(f'가상 레이더 → {dest}/AE-forklift01/radar ({HZ}Hz, 30초 반복, Ctrl+C 종료)')
start, last = time.time(), -1
while True:
    now = time.time()
    tg = scene(now - start)
    try:
        post({'ts': round(now, 2), 'targets': [tg] if tg else [], 'src': 'sim'})
    except Exception as e:
        print('!! 업로드 실패:', e)
    sec = int(now - start)
    if sec != last:
        last = sec
        d = math.hypot(tg['x'], tg['y']) / 1000 if tg else None
        stat = f' | MQTT 보냄 {mq.sent}, 성공 {mq.ok}, 실패 {mq.failed}' if TRANSPORT == 'mqtt' else ''
        print(f'[{sec % 30:2d}s] ' + (f'거리 {d:.2f} m, v={tg["v"]} cm/s' if tg else '표적 없음') + stat)
    time.sleep(max(0, 1 / HZ - (time.time() - now)))
