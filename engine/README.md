# SafeZone 위험판단 엔진 MVP
## MQTT 알림 입출력 — 독립 시험용

`--transport mqtt-notification`은 paho-mqtt 2.x와 정확한 `--mqtt-topic`을 요구한다. 현재 구현은 관찰된 tinyIoT의 직접 `m2m:sgn` JSON을 읽고 기존 radar 판정에 전달한다. SUB 리소스는 자동 생성하지 않으며, CSE의 SUB 및 브로커 토픽은 별도로 구성해야 한다. 실험 환경에서 `nu=mqtt://127.0.0.1:1883/CsafezoneNotify/json`은 `/oneM2M/req/safezone-mqtt-test/CsafezoneNotify/json`에 직접 `m2m:sgn`을 생성했다. 이는 해당 시험용 tinyIoT 버전의 동작이며 다른 버전도 같다고 단정하지 않는다.

`--mqtt-events --mqtt-cse-id <슬래시 없는 ID>`를 함께 주면 events CIN 생성도 MQTT를 사용한다. 요청의 rqi를 응답과 대조하고 rsc=2001을 확인한다. 응답 timeout은 생성 여부를 알 수 없으므로 같은 상태를 자동 재시도하지 않고 오류를 기록한다. 다른 상태가 생기거나 운영자가 CSE를 확인해 해결하기 전에는 해당 상태의 저장 여부가 미확인이다. HTTP 출력을 계속 쓰려면 `--mqtt-events`를 생략한다.

브로커가 끊어지면 UNKNOWN을 기록하고 재연결·재구독을 시도한다. 반복 CIN ri는 중복 판정하지 않으며 retained 및 오래 대기한 메시지를 거부한다. 수신 시각은 엔진 수신 monotonic 기준이며, 네트워크에서 오래 지연된 메시지를 모두 식별한다고 보장하지 않는다. 시험용 stale 값은 실제 속도 측정 후 결정해야 한다.

실제 시험 CSE의 구독 검증 메시지는 rqi 없는 직접 `m2m:sgn`이었고 CSE는 앱 응답 없이 SUB를 생성했다. 본 어댑터는 이 검증 알림을 기록만 하며, 표준 oneM2M 검증 응답을 보내지 않는다. SUB 검증 응답·MQTT 접근 인증·TLS·timeout 후 저장 여부 확인 및 재처리 정책은 미구현/미검증이다. 실제 장치의 alert 제어에는 사용하지 않는다.

```bash
python -m pip install -r engine/requirements-mqtt.txt
python -m engine.main --transport mqtt-notification --mqtt-topic '<알림 토픽>' --mqtt-events --mqtt-cse-id '<CSE ID>'
```



## 먼저 확인할 항목 — 실제 연결 전에 우선 처리

> [!IMPORTANT]
> 아래 항목은 현재 코드가 실제 레이더·tinyIoT에 연결되어 검증되지 않아 남아 있는 전제다. 특히 **P0 두 항목을 확인하기 전에는 정상 복귀 동작이나 실제 장치 제어가 검증됐다고 보면 안 된다.**

- [ ] **P0 · 레이더 CIN 실제 예시 확보:** 실행 중 tinyIoT의 `AE-forklift01/radar/la` 응답 한 건을 저장해 `ri`, `con`, `targets`, `x/y` 단위가 코드의 가정과 맞는지 확인한다. 현재 입력 경로와 필드 형식은 저장소 README 예시를 바탕으로 한 가정이다.
- [ ] **P0 · 레이더가 빈 프레임도 계속 보내는지 확인:** 이 엔진은 새 CIN이 오지 않으면 stale `UNKNOWN`으로 바뀐다. 저장소 README에는 표적이 있을 때만 업로드한다고 적혀 있어, 사람이 화면에서 나가도 새 빈 프레임이 오지 않는다면 엔진은 `SAFE`로 복귀하지 않는다. `targets: []`를 포함한 주기적 heartbeat를 실제로 받을 수 있는지 확인하고, 아니면 레이더 업로더를 보완한다.
- [ ] **P1 · tinyIoT 입출력 확인:** RPi에서 `la` GET이 성공하는지와 `AE-riskengine/events` POST 후 CIN이 실제 생성되는지 응답 및 리소스 조회로 확인한다. HTTP 요청 성공 로그만으로 등록 검증을 끝내지 않는다.
- [ ] **P1 · 제어 경로 확인:** 현재 MVP는 `events`에 판정 기록만 쓰며 모터·LED·부저 명령을 보내지 않는다. 장치 제어에는 alert CIN 작성 규칙과 SUB/notification 설정, `UNKNOWN` 때의 fail-safe 동작 확인이 추가로 필요하다.
- [ ] **P2 · 좌표·표적 추적 조건 확인:** 표적 슬롯이 사람을 연속해서 가리키는지, 지게차 선회 시 레이더 좌표 회전을 어떻게 보정할지, 레이더 설치 오프셋과 차체 외곽을 어떻게 반영할지 확인한다.

## 이 프로그램이 하는 일

라즈베리파이에서 실행하는 Python 위험판단 AE다. 레이더 CIN에서 표적의 2D 좌표를 읽고, 현재 거리와 연속 좌표로 추정한 상대 움직임을 이용해 `SAFE`, `WARNING`, `DANGER`, `UNKNOWN`을 판정한다. 판정 상태가 바뀌면 `AE-riskengine/events`에 oneM2M CIN으로 기록한다.

```text
tinyIoT의 레이더 CIN
        ↓ polling (현재 기본) 또는 SUB notification (선택 가능)
공통 CIN 정규화 → 거리·CPA 계산 → 위험 상태
        ↓ 상태 변경 시
AE-riskengine/events에 이벤트 CIN 등록
```

**이 MVP는 장비를 정지·감속시키거나 경보기를 울리지 않는다.** 레이더에서 실제 CIN을 받아오는 경로와 CSE에 이벤트를 등록하는 경로도 아직 실행 중 서버에서 검증되지 않았다.

## 판정 의미와 상태 규칙

- 현재 거리 기준은 warning `3.0 m`, danger `1.5 m`다. 이 값은 시연용 초기 가설이며 산업안전 기준이 아니다.
- `t_cpa_s`는 일정한 상대속도가 유지된다고 가정했을 때 **최근접 위치에 도달하는 시각**이다. 위험 반경에 **처음 진입하는 시각**이 아니다.
- `d_cpa_m`는 `t_cpa_s` 시점의 예측 최소 거리다. MVP는 `d_cpa_m`가 임시 CPA 반경 `1.0 m` 안이고 최근접 시각이 warning `3.0 s` / danger `1.5 s` 이내일 때 CPA 경고를 낸다. 위험 반경 최초 진입 시각은 계산하지 않는다.
- 위험도 우선순위는 `DANGER > WARNING > UNKNOWN > SAFE`다. 직접 거리 위험은 속도 추정이 안 되어도 판정한다.
- 잘못된 입력, polling/notification 오류, 최초 입력 전 상태, 새 CIN이 1초 넘게 오지 않은 상태는 `UNKNOWN`이다. 데이터 이상을 `SAFE`로 간주하지 않는다.
- 표적이 사라지거나 슬롯이 바뀌면 1초의 유예 동안 기존 `WARNING`/`DANGER`를 유지한다. 이전 위험이 없거나 연결이 불확실하면 `UNKNOWN`이다. 동일 슬롯의 비현실적인 위치 점프는 속도·CPA 추정을 중단하고 거리만으로 직접 위험을 확인한다.
- 유효한 빈 프레임(`targets: []`)이 유예 이후 계속 도착하면 `SAFE`로 돌아갈 수 있다. 프레임 자체가 오지 않으면 `UNKNOWN`이다.

## 구현 가정 — 확인된 사실과 분리

아래는 현재 구현이 전제로 삼는 값이다. 실제 데이터와 다르면 코드를 고치기보다 먼저 해당 설정/정규화 지점을 확인하면 된다.

| 전제 | 현재 처리 | 수정 지점 |
|---|---|---|
| 레이더 최신 CIN은 `AE-forklift01/radar/la`에서 GET 가능 | 기본 경로에서 polling | `ONEM2M_RADAR_PATH` |
| oneM2M CIN에는 `ri`가 있음 | polling 중복 제거 및 notification 중복 전달 방지에 사용. 없으면 입력 오류 처리 | `RiskApplication.accept_message()` |
| CIN `con`은 객체 또는 JSON 문자열이고 `targets` 배열을 포함 | 두 형식을 모두 허용. 표적의 `x`,`y`는 mm, `v`는 선택적인 cm/s 원시값 | `normalize_radar_cin()` |
| 센서 `ts`는 Unix 초 | `sensor_ts_unix_s`에 보존만 하고 속도·신선도 계산에는 쓰지 않음 | `normalize_radar_cin()` |
| Pi 수신 시각은 처리 서버의 시계 | 속도 추정·stale·표적 소실 시간에 monotonic 수신 시각을 사용. 별도로 서버 수신 Unix 시각/UTC도 기록 | `RiskEngine.process_frame()` |
| 같은 표적을 연속 프레임에서 슬롯/배열 위치로 연결 가능 | `slot`, 없으면 `id`, 그것도 없으면 배열 순번을 임시 키로 사용. 영구적인 사람 ID로 보지 않음 | `normalize_radar_cin()`, 표적 jump gate |
| LD2450의 `v`만으로 2D 이동 방향을 알 수 없음 | `v`는 기록용. `vx`,`vy`는 같은 키의 연속 `x`,`y`와 서버 monotonic `dt`로 계산 | `RiskEngine._evaluate_target()` |
| MVP 중 레이더와 지게차의 방향은 일정 | 레이더 좌표계에서 상대속도를 계산. 선회하면 좌표 회전이 속도 추정에 섞임 | 후속 yaw 보정 필요 |
| 레이더 원점으로부터 잰 거리를 근사값으로 사용 | 레이더 설치 오프셋과 지게차 물리 외곽은 아직 반영하지 않음 | CPA 반경 및 좌표 보정 후속 작업 |
| 테스트 임계값을 환경에 맞춰 조정할 수 있음 | 현재 기본값은 모두 가설값. 이벤트에도 적용 파라미터를 기록 | `config.py` / 아래 환경 변수 |
| 이벤트 기록이 우선 | 상태 변경 때만 `AE-riskengine/events`에 CIN 등록. alert CIN이나 장치 제어는 하지 않음 | `ONEM2M_EVENTS_PATH`, 후속 제어 연동 |

## polling에서 SUB notification으로 바꾸기

두 방식은 같은 `RiskApplication.accept_message()`와 `normalize_radar_cin()`을 사용하므로 전송부만 바꾸고 판정 로직은 유지한다. notification 입력은 `m2m:sgn.nev.rep.m2m:cin` 포장을 풀고 `vrq` 확인 요청에는 oneM2M 성공 응답을 보낸다.

현재 구독이 없을 때는 저장소 루트에서:

```powershell
python -m engine.main --transport polling
```

구독을 설정한 뒤 notification 수신으로 전환하려면:

```powershell
python -m engine.main --transport notification --listen 0.0.0.0 --port 8081
```

그 다음 tinyIoT의 `AE-forklift01/radar` SUB `nu`를 `http://<RPi 주소>:8081/notify`로 설정해야 한다. 이 프로그램은 SUB를 생성하지 않는다. CSE에서 RPi 주소/포트로 접근 가능한지도 확인한다.

## 설정값

| 환경 변수 | 기본값 | 의미 |
|---|---:|---|
| `ONEM2M_CSE_BASE` | `http://127.0.0.1:3000/TinyIoT-MN` | CSE base URI. Pi의 실제 설정이 다르면 환경 변수로 지정 |
| `ONEM2M_RADAR_PATH` | `/AE-forklift01/radar/la` | 최신 레이더 CIN 경로 |
| `ONEM2M_EVENTS_PATH` | `/AE-riskengine/events` | 이벤트 CNT 경로 |
| `ONEM2M_ORIGIN` / `ONEM2M_RVI` | `Criskengine` / `3` | oneM2M Origin / Release Version |
| `ONEM2M_POLL_INTERVAL_S` / `ONEM2M_HTTP_TIMEOUT_S` | `0.1` / `1.0` | polling 주기 / HTTP timeout |
| `RISK_WARNING_DISTANCE_M` / `RISK_DANGER_DISTANCE_M` | `3.0` / `1.5` | 가설적 현재 거리 기준 |
| `RISK_WARNING_TTC_S` / `RISK_DANGER_TTC_S` | `3.0` / `1.5` | 가설적 최근접 시각 기준 (`t_cpa_s`) |
| `RISK_CPA_RADIUS_M` / `RISK_CPA_HORIZON_S` | `1.0` / `3.0` | 가설적 최근접 거리 / 예측 범위 |
| `RISK_MIN_SPEED_MPS` | `0.05` | 이보다 느리면 CPA 무효 |
| `RISK_MAX_SAMPLE_INTERVAL_S` | `0.75` | 이보다 긴 수신 간격이면 속도·CPA 무효 |
| `RISK_STALE_AFTER_S` | `1.0` | 새 CIN 부재 시 UNKNOWN 전환 시간 |
| `RISK_TARGET_LOSS_GRACE_S` | `1.0` | 표적 소실 유예 시간 |
| `RISK_MAX_TARGET_JUMP_M` | `2.5` | 같은 표적의 비현실적 위치 점프 제한 |

## 검증

```powershell
python -m unittest engine.test_risk_engine -v
```

현재 모의 CIN 단위 테스트 12개가 통과한다. 실제 LD2450 데이터, 실행 중 tinyIoT의 GET/POST, SUB 알림 전달, LED·부저·모터 동작은 이 테스트 범위에 포함되지 않는다.
