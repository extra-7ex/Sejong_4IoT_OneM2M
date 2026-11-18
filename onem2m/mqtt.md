# MQTT 바인딩 규격 (디바이스 ↔ MN-CSE)

ESP8266 등 디바이스가 MQTT로 tinyIoT MN-CSE에 oneM2M 요청을 보내 CIN을 만드는 규격이다.
토픽·포맷은 tinyIoT 소스(`source/server/mqttClient.c`)에서 확인했고, `mosquitto_pub`/`mosquitto_sub`로 디바이스를 흉내 내 노트북(시뮬레이터)과 실제 Pi에서 왕복을 검증했다.

- 상태: 브로커 연결, 토픽, 메시지 포맷, 권한, CIN 생성·`la` 조회 검증 완료
- 미검증: 실제 ESP8266 펌웨어에서의 publish (장비 미확보)
- 기존 HTTP 스크립트(`setup_onem2m.sh`, `sub_alert_node.sh`)는 그대로 쓴다. 이 문서는 MQTT 경로만 추가로 다룬다.

---

## 1. 브로커와 tinyIoT 설정

MN-CSE와 같은 Pi에 Mosquitto(오픈소스 MQTT 브로커)를 띄운다.

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo tee /etc/mosquitto/conf.d/tinyiot.conf > /dev/null << 'EOF'
listener 1883 0.0.0.0
allow_anonymous true
EOF
sudo systemctl enable --now mosquitto
```

tinyIoT `config.h`에서 `// #define ENABLE_MQTT`의 주석을 풀고 다시 빌드한다. Makefile이 `config.h` 변경을 추적하지 않으므로 반드시 `make clean && make`로 빌드한다.

```c
#define ENABLE_MQTT
#define MQTT_HOST "127.0.0.1"   // 같은 Pi의 Mosquitto
// MQTT_PORT 1883 (TLS 미사용 시 기본값)
```

- MQTT는 MN에서만 켠다. IN까지 같은 브로커에 붙으면 두 CSE가 같은 ClientID(`MQTT_CLIENT_ID "TinyIoT"`)를 써서 서로 연결을 끊는다.
- 익명 허용은 시험용이다. 운영 전 계정·ACL을 설정해야 한다.

정상 기동 로그 (`CSE_BASE_RI`가 `id-mn`일 때):

```
[MQTT]: MQTT Subscribe Success: Topic /oneM2M/req/+/id-mn/#, QoS 1
[MQTT]: MQTT Subscribe Success: Topic /oneM2M/resp/id-mn/+/#, QoS 1
```

---

## 2. 토픽

`<cse-ri>`는 `config.h`의 `CSE_BASE_RI` 값이다. 현재 Pi MN은 `id-mn`, IN은 `id-in`이다.

| 방향 | 토픽 | 디바이스 동작 |
|---|---|---|
| 요청 (디바이스 → CSE) | `/oneM2M/req/<originator>/<cse-ri>/json` | publish |
| 응답 (CSE → 디바이스) | `/oneM2M/resp/<originator>/<cse-ri>/json` | subscribe |

- 요청·응답 모두 originator가 앞, cse-ri가 뒤다 (`mqttClient.c` 313행, 993행).
- 토픽에 들어가는 값은 CSEBase 이름(`CSE_BASE_NAME`)이 아니라 `CSE_BASE_RI`다. [CSE 명명안](../docs/cse-naming.md)대로 CSE ID를 `/tinyiot-mn`으로 바꾸려면 `CSE_BASE_RI`를 바꿔야 토픽도 `.../tinyiot-mn/json`이 된다. 이 전환은 아직 시험하지 않았다.

---

## 3. 메시지 포맷

최상위가 평평한 JSON이어야 한다. `{"m2m:rqp":{...}}`처럼 감싸면 `Invalid Request`로 거부된다.

| 필드 | 필수 | 의미 |
|---|---|---|
| `op` | 예 | 1=Create, 2=Retrieve, 3=Update, 4=Delete |
| `to` | 예 | 대상 경로. 앞 슬래시 없이 CSEBase 이름부터 |
| `fr` | 예 | originator |
| `rqi` | 예 | 요청 식별자 (요청마다 고유) |
| `rvi` | 예 | `"3"` |
| `ty` | Create 시 | 리소스 타입 (CIN=4) |
| `pc` | Create·Update 시 | 리소스 본문 |

`to`에 앞 슬래시를 붙이면(`/TinyIoT-MN/...`) `rsc:4004`(`URI is invalid`)가 돌아온다.

레이더 CIN 생성 예 (`fr`은 AE를 만든 originator와 같아야 함):

```bash
mosquitto_pub -h <MQTT_BROKER_IP> -t "/oneM2M/req/Cforklift01/id-mn/json" -m \
'{"op":1,"to":"<CSE_BASE_NAME>/<AE_RN>/radar","fr":"Cforklift01","rqi":"req-0001","rvi":"3","ty":4,
  "pc":{"m2m:cin":{"con":"{\"ts\":1731300000,\"targets\":[{\"x\":500,\"y\":0,\"v\":100}]}"}}}'
```

성공하면 응답 토픽으로 `rsc:2001`과 같은 `rqi`가 온다. 이후 `<CSE_BASE_NAME>/<AE_RN>/radar/la`를 조회해 같은 `con`이 들어갔는지 확인한다.

---

## 4. 권한

- AE를 originator `Cforklift01`로 만들면 그 AE의 `aei`가 `Cforklift01`이 되고, 같은 originator로 하위 CNT에 CIN을 쓸 수 있다.
- 다른 originator로 쓰면 권한 오류가 난다. 다른 AE(예: RiskEngine)가 읽거나 쓰려면 ACP가 필요하다(이슈 #6).
- ESP 펌웨어의 `fr`·토픽 originator는 AE를 만든 값과 맞춘다.

---

## 5. 시험 결과

| 구분 | 환경 | 확인 결과 |
|---|---|---|
| 시뮬레이터 (11/9) | 노트북 WSL tinyIoT(IN, `id-in`) + Mosquitto, `mosquitto_pub`/`sub`로 ESP 흉내 | 구독 토픽 `/oneM2M/req/+/id-in/#` 확인. `Cforklift01`로 AE·CNT 생성 후 같은 originator로 레이더 포맷 CIN 생성 → `rsc:2001`, `la` 일치. 실패 재현: `m2m:rqp` 래퍼 → `Invalid Request`, `to` 앞 슬래시 → `rsc:4004` |
| 실제 Pi (11/10) | Raspberry Pi 4B, MN(`id-mn`, 3000, MQTT on) ↔ Pi 내부 IN(`id-in`, 3001), Mosquitto, `mosquitto_pub`로 ESP 흉내 | MN↔IN 등록 `Remote CSE registration check: 200`. MQTT 구독 4개 성공. 토픽 `/oneM2M/req/Cforklift01/id-mn/json`, `to=TinyIoT-mn/forklift01/radar` → `rsc:2001`, `rqi` 일치. `radar/la`에 올린 `ts`·`targets` 그대로 확인 |
| 미시험 | 실제 ESP8266 기기 | 장비 확보 후 |

시험 당시 Pi의 CSEBase 이름은 `TinyIoT-mn`, AE rn은 `forklift01`이었다. 팀 기본값(`TinyIoT-MN`, `AE-forklift01`)과 다르므로, ESP 펌웨어의 `to`는 [CSE 명명안](../docs/cse-naming.md)의 전환이 끝난 뒤 확정한다.

---

## 6. 남은 일

- 실제 ESP8266 펌웨어로 publish 연동
- 구독 알림을 MQTT로 받는 경로 (alert → 경보기 ESP). 소스상 알림 토픽은 `/oneM2M/req/<cse-ri>/<대상>` 형태로 보이며(`mqttClient.c` 635행) 실측 필요
- ESP 쪽 결정 사항: 전송 주기, 빈 프레임 처리, timestamp 생성 위치
