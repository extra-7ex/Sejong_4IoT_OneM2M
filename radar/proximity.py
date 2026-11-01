import serial, math, time, urllib.request

ESP = 'http://192.168.219.104'   # ESP8266 IP
WARN_MM = 500                    # 경고 거리 (mm)
OFF_DELAY = 1.5                  # 이 시간(초) 동안 계속 범위 밖이어야 끔

ser = serial.Serial('/dev/serial0', 256000, timeout=1)
HEAD, TAIL = b'\xAA\xFF\x03\x00', b'\x55\xCC'

def val(b):
    v = int.from_bytes(b, 'little')
    return (v & 0x7FFF) if v & 0x8000 else -(v & 0x7FFF)

def send(cmd):
    try:
        urllib.request.urlopen(f'{ESP}/{cmd}', timeout=1)
        print(f'>> {cmd}')
    except Exception as e:
        print(f'!! {cmd} 전송 실패: {e}')

alarm = False
last_in = 0
send('off')                      # 시작할 때 꺼진 상태로 맞춤
buf = bytearray()

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

    # 잡힌 타겟 중 가장 가까운 거리
    dists = []
    for n in range(3):
        d = f[4+n*8 : 12+n*8]
        if any(d):
            dists.append(math.hypot(val(d[0:2]), val(d[2:4])))
    near = min(dists) if dists else None

    now = time.time()
    if near is not None and near <= WARN_MM:
        last_in = now
        if not alarm:            # 꺼짐 → 켜짐 바뀔 때만 전송
            alarm = True
            print(f'경고! {near:.0f}mm')
            send('on')
    elif alarm and now - last_in >= OFF_DELAY:
        alarm = False
        print('해제')
        send('off')
