import serial, math

ser = serial.Serial('/dev/serial0', 256000, timeout=1)
HEAD, TAIL = b'\xAA\xFF\x03\x00', b'\x55\xCC'

def val(b):  # MSB 1 = 양수, 0 = 음수
    v = int.from_bytes(b, 'little')
    return (v & 0x7FFF) if v & 0x8000 else -(v & 0x7FFF)

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
    for n in range(3):
        d = f[4+n*8 : 12+n*8]
        if not any(d):          # 타겟 없으면 전부 0
            continue
        x, y, v = val(d[0:2]), val(d[2:4]), val(d[4:6])
        print(f"T{n+1} x={x}mm y={y}mm v={v}cm/s dist={math.hypot(x,y):.0f}mm")
