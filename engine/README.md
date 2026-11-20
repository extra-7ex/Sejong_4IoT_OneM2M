# SafeZone 위험판단 엔진 MVP

## 레이더 입력 시각 검사

모든 레이더 CIN은 `con.ts`에 Unix 초를 포함해야 한다. 레이더 업로더와 엔진의
시계가 동기화돼 있어야 한다. 프레임이 `RISK_RADAR_MAX_AGE_S`(기본 3초)보다
오래됐거나 `RISK_RADAR_FUTURE_SKEW_S`(기본 1초)를 넘겨 미래에 있으면 해당
프레임을 처리하지 않고 `UNKNOWN`으로 기록한다. 유효한 빈 `targets: []`는
정상 프레임이다. 시계가 틀리거나 3초 이상 지연되면 정상 센서도 UNKNOWN이
될 수 있으므로 실제 네트워크 지연을 측정해 한계를 설정한다.

입력 시각 검사만으로 CSE 또는 네트워크 단절 시 ESP 정지가 보장되지는 않는다.
UNKNOWN 전송·각 장치 수신, 재접속 시 상태 동기화 및 장치 독립 감시는 별도
검증이 필요하다. 시험에서는 작업자 UNKNOWN 무음, 지게차 UNKNOWN 정지가 목표다.

## MQTT 알림 입출력 — Pi 격리 시험 확인

### Vision 조언과 작업자 alert 시험

`--vision-path /AE-VisionAI/fusedTracks/la`를 지정하면 레이더 판정이 `SAFE`·`WARNING`·`DANGER`일 때마다 MN-CSE에 HTTP GET을 보내 최신 Vision CIN을 확인한다(`UNKNOWN`일 때는 조회하지 않고 그대로 둔다). 주기 타이머 폴링이 아니라 레이더 입력에 따른 조회다. Vision 입력이 없거나 오래됐거나 `cam_ok=false`이거나 유효하지 않으면 레이더 판정을 유지한다. 시계가 동기화됐다는 가정이 필요하다. 모든 Vision 조언은 Vision 결과의 `cam_ok`와 `radar_ok`가 모두 `true`일 때만 쓴다. `radar_ok`가 없거나 `true`가 아니면 조언을 적용하지 않고 `vision_radar_unavailable`을 기록한다(VisionAI가 레이더 입력 없이 카메라만으로 만든 결과를 믿지 않기 위해서다).

| 규칙 | 조건 | 결과 |
|---|---|---|
| 카메라 단독 올리기 | 레이더 `SAFE`, Vision `ts` 3초 이내, `camera_only` + `raise` | `WARNING` |
| 자세 올리기 | 레이더 `WARNING` 표적, 같은 슬롯(`radar_id`)이고 거리 차 0.5m 이내인 `confirmed` + `raise`, 자세 `crouching`·`lying`, Vision 3초 이내 | 그 표적 `DANGER` |
| 유령 낮추기 (**기본 꺼짐**, `VISION_GHOST_LOWER_ENABLED=true`로 켬) | 레이더 `DANGER` 표적, 같은 슬롯이고 거리 차 0.5m 이내인 `ghost_suspect` + `lower_to_caution`, 표적 거리 1m 초과, Vision **1초** 이내 | 그 표적 `WARNING` (`SAFE`로는 내리지 않음) |

표적마다 조정한 뒤 가장 높은 단계를 최종 판정으로 쓴다. 다른 표적이 진짜 `DANGER`면 유령을 낮춰도 `DANGER`다. 직전 표적을 잃어 이전 위험을 유지 중인 표적(`held_previous_risk`)과 연결이 불확실한 표적은 조정하지 않는다. 조정 내용은 판정의 `vision_adjustments`, 레이더만의 판정은 `radar_status`에 남는다.

**해제 지연:** `WARNING`·`DANGER`에서 `SAFE`로 내려갈 때는 `SAFE`가 3초 이어져야 내려간다(팀 규칙 "안전 상태 3초 유지 후 재가동"). 그동안은 직전 위험 단계를 `reason=release_hold_waiting_for_safe`로 유지한다. `DANGER`→`WARNING`과 모든 상향, `UNKNOWN`은 바로 반영한다. `UNKNOWN`이 끼면 SAFE 연속 시간은 처음부터 다시 센다. 주기 `tick()`은 레이더가 신선한 동안 Vision이 반영된 마지막 판정을 다시 쓰므로, Vision이 올린 단계를 레이더 단독 판정으로 되돌리지 않는다.

| 환경 변수 | 기본값 | 의미 |
|---|---|---|
| `VISION_MAX_AGE_S` | 3.0 | 올리기에 쓰는 Vision 최대 나이 |
| `VISION_LOWER_MAX_AGE_S` | 1.0 | 유령 낮추기에 쓰는 Vision 최대 나이 |
| `VISION_GHOST_MIN_DISTANCE_M` | 1.0 | 이 거리 안의 표적은 낮추지 않음 |
| `VISION_MATCH_TOLERANCE_M` | 0.5 | Vision 표적과 레이더 표적의 거리 차 허용 |
| `VISION_FUTURE_SKEW_S` | 0.5 | Vision `ts`가 미래로 허용되는 오차 |
| `RISK_RELEASE_HOLD_S` | 3.0 | `SAFE` 해제 지연 (0이면 끔) |
| `VISION_GHOST_LOWER_ENABLED` | false | 유령 낮추기 사용. 실제 사람을 놓칠 위험을 실장비에서 확인하기 전에는 끈다 |

위 규칙은 단위 시험(`engine/test_vision_advice.py`)으로만 확인했다. 실제 VisionAI fusedTracks와 실제 LD2450으로는 아직 시험하지 않았다.

`--mqtt-events`와 `--mqtt-alert-path /AE-worker01/alert-test`를 함께 지정하면 미리 만든 단일 시험 작업자 CNT에 상태 변경 시 `level`, `dist`(mm), `ttc`(null)를 기록한다. alert 발행은 기본적으로 꺼져 있다. events와 alert는 각자 응답과 불확실 상태를 추적한다. 같은 상태의 결과가 불확실하면 자동 재전송하지 않는다.

핵심 확인사항: 시험용 작업자 한 명의 경로를 명시한다. 이 시험은 그 한 작업자에게 전체 위험 상태를 전달하는 임시 전제를 쓴다. 레이더 표적과 작업자 ESP의 매핑은 미정이므로 실제 작업자에게 경보를 보내는 구성으로 간주하지 않는다. 현재 worker_node는 `unknown`을 무음으로 처리한다. 실제 수신과 부저를 검증할 때까지 기존 `LOCAL_DECISION`을 유지하고 운영 CNT의 작성자는 한 번에 하나로 둔다. 단말이 구독하는 경로와 시험 CNT는 일치해야 한다. 시험 ACP는 Pi에서 확인했지만 운영 ACP, 재접속 시 상태 동기화와 실제 장비 연동은 미검증이다.

### Pi ARM64 통합 시험 결과 (2026-11-17)

Pi의 `TinyIoT-MN`과 Mosquitto에서 운영 리소스와 분리된 시험 CNT를 사용했다. 레이더 CIN은 MQTT 요청으로 만든 모의 데이터였고, RiskEngine은 radar SUB 알림을 MQTT로 받았다. `events`와 `alert` CIN은 MQTT 요청으로 생성했으며, oneM2M 성공 응답 `rsc=2001`과 시험 리소스 조회를 확인했다. 별도 MQTT 관찰 구독은 alert 알림 5건을 받았다. 실제 ESP8266이나 부저를 사용한 것은 아니다.

Vision도 실제 VisionAI 출력이 아니라 모의 `fusedTracks` CIN으로 시험했다. 시험 전용 ACP를 통해 `Criskengine`이 이 CNT를 읽었고, 테스트 CIN은 HTTP로 생성했다. 신선한 `camera_only + raise`는 Radar SAFE를 WARNING으로 올렸으며 raise가 없는 신선한 결과에서는 SAFE를 유지했다. 별도 연속 프레임으로 CPA WARNING(`t_cpa_s=2.5936`, `d_cpa_m=0`)과 DANGER(`t_cpa_s=0.9113`, `d_cpa_m=0`), 입력 만료 후 UNKNOWN을 확인했다. 한 첫 실행은 샘플 간격이 맞지 않아 WARNING만 확인했고, 간격을 제어해 재시험한 결과 DANGER를 확인했다.

alert CIN은 기존 호환 형식인 `level`, `dist`(mm), `ttc`(null)를 쓴다. CPA 값은 `events`의 `t_cpa_s`와 `d_cpa_m`에서 확인한다. 실제 LD2450 업로더 입력, VisionAI의 실제 fusedTracks 생성, 운영 ACP, 작업자 ESP 수신, LED·부저, 재접속 후 상태 동기화는 검증하지 않았다. 실제 수신·부저 검증 전까지 기존 `LOCAL_DECISION`을 유지하고 운영 CNT의 작성자는 한 번에 하나로 둔다.

시험 call flow는 레이더 CIN notification → 거리·CPA 판정 → (레이더 SAFE일 때) fusedTracks HTTP GET → events/alert MQTT CIN 생성 → 시험 구독자의 MQTT alert 알림이다. 이는 실제 장치 경보를 확인한 결과가 아니다.

`--transport mqtt-notification`은 paho-mqtt 2.x와 정확한 `--mqtt-topic`을 요구한다. 현재 구현은 관찰된 tinyIoT의 직접 `m2m:sgn` JSON을 읽고 기존 radar 판정에 전달한다. SUB 리소스는 자동 생성하지 않으며, CSE의 SUB 및 브로커 토픽은 별도로 구성해야 한다. 실험 환경에서 `nu=mqtt://127.0.0.1:1883/CsafezoneNotify/json`은 `/oneM2M/req/safezone-mqtt-test/CsafezoneNotify/json`에 직접 `m2m:sgn`을 생성했다. 이는 해당 시험용 tinyIoT 버전의 동작이며 다른 버전도 같다고 단정하지 않는다.

`--mqtt-events --mqtt-cse-id <슬래시 없는 ID>`를 함께 주면 events CIN 생성도 MQTT를 사용한다. 요청의 rqi를 응답과 대조하고 rsc=2001을 확인한다. 응답 timeout은 생성 여부를 알 수 없으므로 같은 상태를 자동 재시도하지 않고 오류를 기록한다. 다른 상태가 생기거나 운영자가 CSE를 확인해 해결하기 전에는 해당 상태의 저장 여부가 미확인이다. HTTP 출력을 계속 쓰려면 `--mqtt-events`를 생략한다.

브로커가 끊어지면 UNKNOWN을 기록하고 재연결·재구독을 시도한다. 반복 CIN ri는 중복 판정하지 않으며 retained 및 오래 대기한 메시지를 거부한다. 수신 시각은 엔진 수신 monotonic 기준이며, 네트워크에서 오래 지연된 메시지를 모두 식별한다고 보장하지 않는다. 시험용 stale 값은 실제 속도 측정 후 결정해야 한다.

실제 시험 CSE의 구독 검증 메시지는 rqi 없는 직접 `m2m:sgn`이었고 CSE는 앱 응답 없이 SUB를 생성했다. 본 어댑터는 이 검증 알림을 기록만 하며, 표준 oneM2M 검증 응답을 보내지 않는다. SUB 검증 응답·MQTT 접근 인증·TLS·timeout 후 저장 여부 확인 및 재처리 정책은 미구현/미검증이다.

```bash
python -m pip install -r engine/requirements-mqtt.txt
python -m engine.main --transport mqtt-notification --mqtt-topic '<알림 토픽>' --mqtt-events --mqtt-cse-id '<CSE ID>'
```



## 먼저 확인할 항목 — 실제 연결 전에 우선 처리

> [!IMPORTANT]
> 아래 항목은 현재 코드가 실제 레이더·tinyIoT에 연결되어 검증되지 않아 남아 있는 전제다. 특히 **P0 두 항목을 확인하기 전에는 정상 복귀 동작이나 실제 장치 제어가 검증됐다고 보면 안 된다.**

- [ ] **P0 · 레이더 CIN 실제 예시 확보:** 실행 중 tinyIoT의 `AE-forklift01/radar/la` 응답 한 건을 저장해 `ri`, `con`, `targets`, `x/y` 단위가 코드의 가정과 맞는지 확인한다. 현재 입력 경로와 필드 형식은 저장소 README 예시를 바탕으로 한 가정이다.
- [ ] **P0 · 레이더가 빈 프레임도 계속 보내는지 확인:** 이 엔진은 새 CIN이 오지 않으면 stale `UNKNOWN`으로 바뀐다. 코드에 빈 프레임 전송이 추가됐지만 실제 장비에서 확인되지 않았다. 사람이 화면에서 나가도 새 빈 프레임이 오지 않는다면 엔진은 `SAFE`로 복귀하지 않는다. `targets: []`를 포함한 주기적 heartbeat를 실제로 받을 수 있는지 확인하고, 아니면 레이더 업로더를 보완한다.
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

- 현재 거리 기준은 warning `1.0 m`, danger `0.5 m`다(11/19, 지게차 노드 `radar_node.py`의 `WARN_MM`·`DANGER_MM`과 통일). 예측 최근접 반경도 `0.5 m`다. 이 값은 시연용 초기 가설이며 산업안전 기준이 아니다.
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
| 센서 `ts`는 Unix 초 | 엔진 입력 단계에서 현재 시각과 비교해 오래되거나 미래인 프레임을 UNKNOWN으로 처리한다. 속도 계산은 monotonic 수신 시각을 쓴다. | `RiskApplication.accept_message()` |
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
| `RISK_WARNING_DISTANCE_M` / `RISK_DANGER_DISTANCE_M` | `1.0` / `0.5` | 가설적 현재 거리 기준 |
| `RISK_WARNING_TTC_S` / `RISK_DANGER_TTC_S` | `3.0` / `1.5` | 가설적 최근접 시각 기준 (`t_cpa_s`) |
| `RISK_CPA_RADIUS_M` / `RISK_CPA_HORIZON_S` | `0.5` / `3.0` | 가설적 최근접 거리 / 예측 범위 |
| `RISK_MIN_SPEED_MPS` | `0.05` | 이보다 느리면 CPA 무효 |
| `RISK_MAX_SAMPLE_INTERVAL_S` | `0.75` | 이보다 긴 수신 간격이면 속도·CPA 무효 |
| `RISK_STALE_AFTER_S` | `1.0` | 새 CIN 부재 시 UNKNOWN 전환 시간 |
| `RISK_RADAR_MAX_AGE_S` | `3.0` | 센서 시각이 이 시간보다 오래되면 UNKNOWN |
| `RISK_RADAR_FUTURE_SKEW_S` | `1.0` | 센서 시각이 현재보다 이 시간 넘게 앞서면 UNKNOWN |
| `RISK_TARGET_LOSS_GRACE_S` | `1.0` | 표적 소실 유예 시간 |
| `RISK_MAX_TARGET_JUMP_M` | `2.5` | 같은 표적의 비현실적 위치 점프 제한 |

## 검증

```powershell
python -m unittest engine.test_risk_engine -v
```

현재 모의 CIN 단위 테스트 12개가 통과한다. 실제 LD2450 데이터, 실행 중 tinyIoT의 GET/POST, SUB 알림 전달, LED·부저·모터 동작은 이 테스트 범위에 포함되지 않는다.

### 빈 프레임 MQTT 입력 모의 검증

MQTT 콜백·알림 JSON과 모의 events 기록을 사용한 단위 시험에서 표적 DANGER → 0.5초 간격 빈 프레임 수신 시 유예 동안 DANGER 유지 → 빈 프레임 1초 유지 후 SAFE → 새 프레임이 1초 넘게 없으면 UNKNOWN을 확인했다. 이는 실제 브로커, tinyIoT 또는 레이더의 통합 시험이 아니다. 전체 엔진 단위 테스트 23개 통과. PR #13의 MQTT 업로더와 엔진을 독립 시험용 tinyIoT·Mosquitto에서 모의 직렬 프레임으로 연결했다. DANGER → 빈 프레임 유지 후 SAFE → 입력 중단 후 UNKNOWN 및 events CIN 조회를 확인했다. 시험에서는 관리자 Origin과 stale 2초를 사용했다. 공용 MN 권한과 실제 센서·장비는 미검증이다. slot이 같은 표적을 유지한다고 잠정 가정하며 실제 슬롯 연속성은 미검증이다.
