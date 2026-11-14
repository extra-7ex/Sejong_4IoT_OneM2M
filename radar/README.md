# 레이더 (LD2450 → tinyIoT MN)

| 파일 | 하는 일 |
|---|---|
| `radar_node.py` | Pi UART(`/dev/serial0`)로 LD2450을 읽어 `AE-forklift01/radar`에 CIN을 올린다. 임시 거리 판단(`LOCAL_DECISION`)으로 `alert`도 쓴다 |
| `sim_rader.py` | 레이더 없이 같은 형식의 CIN을 10 Hz로 올리는 가상 레이더 (30초 접근·이탈 반복) |
| `onem2m_mqtt.py` | 두 프로그램이 함께 쓰는 oneM2M MQTT 클라이언트 |
| `ld2450.py`, `proximity.py` | 초기 시험용 |

## 통신 방식

기본은 **oneM2M MQTT 바인딩**이다. 규격은 `onem2m/mqtt.md`와 같다.

- 요청 토픽 `/oneM2M/req/Cforklift01/tinyiot-mn/json`, 응답 토픽 `/oneM2M/resp/Cforklift01/tinyiot-mn/json`
- 메시지는 감싸지 않은 JSON `{op, to, fr, rqi, rvi, ty, pc}`. `to`는 `TinyIoT-MN/AE-forklift01/radar`처럼 앞에 `/` 없이 쓴다
- 응답은 백그라운드에서 확인하고 실패(`rsc`가 2000/2001이 아님)만 출력한다

```bash
sudo apt install python3-serial python3-paho-mqtt     # 처음 한 번

python3 radar/radar_node.py                            # MQTT, 같은 Pi의 브로커
TRANSPORT=http python3 radar/radar_node.py             # 예전 HTTP 방식
python3 radar/sim_rader.py                             # 가상 레이더 (MQTT)
```

| 환경 변수 | 기본값 | 의미 |
|---|---|---|
| `TRANSPORT` | `mqtt` | `mqtt` 또는 `http` |
| `CSE_NAME` / `CSE_RI` | `TinyIoT-MN` / `tinyiot-mn` | CSEBase 이름 / MQTT 토픽에 쓰는 `CSE_BASE_RI` |
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1` / `1883` | 브로커 (MN과 같은 Pi) |
| `CSE_URL` | `http://<Pi IP>:3000/TinyIoT-MN` | HTTP일 때 주소 |
| `SERIAL_PORT` | `/dev/serial0` | LD2450 UART |

## radar CIN 형식

```json
{"ts": 1794372339.82, "targets": [{"slot": 0, "x": 283, "y": 545, "v": 0}]}
```

`x`, `y`는 mm, `v`는 cm/s, `slot`은 LD2450의 표적 칸(0–2)이다. 지금은 표적이 있을 때만 0.5초 간격으로 올린다.

## 시험 (2026-11-14, Pi, MN `TinyIoT-MN`)

- `sim_rader.py` MQTT 15초 두 번: 각 148건 보냄, 148건 저장, 148건 응답 `2001`, 오류 0
- `radar_node.py`를 가짜 LD2450 직렬 포트로 실행: radar CIN이 `slot` 포함해 저장됨, 임시 판단 alert가 safe → danger(490 mm) → safe로 바뀜
- 그 alert가 MQTT 구독(`onem2m/sub_alert_node_mqtt.sh`)으로 `/oneM2M/req/tinyiot-mn/Calertnode/json`에 그대로 전달됨 (ESP 대신 `mosquitto_sub`로 확인)
- 실제 LD2450과 실제 ESP8266으로는 아직 시험하지 않았다
