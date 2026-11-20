# SafeZone 아키텍처와 통합 상태

## 문서 범위

팀 공유 정보, GitHub 코드와 별도 시험 결과를 정리한다. 목표 구성, 관제 경로와 아래 통합 기록을 2026-11-17에 다시 대조했다. **현재 프로토타입**, **코드·모의 시험**, **미검증 목표**는 서로 다르다. 각 시험의 서버·DB와 데이터 출처를 확인하고, 단일 시험 결과로 실제 장비 전체 연동이나 산업안전 성능을 주장하지 않는다.

- 저장소 기준: [Draft PR #14](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/14)는 RiskEngine MQTT radar 알림 입력과 `events` 기록의 기반이다. 이 문서의 Pi 검증과 `alert`·Vision 조언 코드 변경은 별도 Draft PR로 제안하며, #14나 `main`에 직접 푸시하지 않는다.
- [Vision MQTT 입력 PR #21](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/21)은 VisionAI가 레이더 알림을 받는 경로다. RiskEngine의 fusedTracks 접근은 아래 Pi 시험에서 별도로 검증한 HTTP GET이며, #21의 레이더 입력 경로와 혼동하지 않는다.
- MEC 작업은 [실험 PR #16](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/16), [연동 AE PR #18](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/18), [Pi MN 시험 PR #19](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/19)에서 이어진다. 각각의 테스트 범위와 미검증 항목은 해당 PR에 한정한다.
- 현태의 설명: LD2450은 Pi UART에 직접 연결되어 있으며 ESP8266은 레이더와 직접 연결하지 않고 tinyIoT의 HTTP 알림을 받는다. 장비별 현재 펌웨어·동작은 재확인이 필요하다.
- 광민의 보고: Pi MN과 노트북 IN의 연결 시험 성공. 다른 시험에서는 Pi 내부 IN도 사용했다. CSE 등록과 `events`의 IN 전달은 별도 검증이다.
- [Vision PR #9](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/9): 실제 radar CIN 예시를 Vision이 읽었고, MQTT·HTTP 입력/출력과 녹화 영상으로 시험했다고 보고했다. PR은 작성 당시 열린 상태였으며 해당 보고의 전체 재현 여부는 별도 기록한다.

## 현재 Pi 구성 (2026-11-20)

최신 구성, 실장비 시험, ACP 및 네트워크 복구 절차는 [Pi 운영 상태](pi-operating-state.md)를 기준으로 한다. 현재 엔진은 HTTP로 radar와 fusedTracks를 조회하고 events 및 경보 그룹에 쓴다. MEC 발견은 수동 등록한 시험 서비스를 통해 Pi에서 확인했으며, 서비스 자동 등록과 다중 장비 선택은 확장 과제다. VisionAI는 시험 후 중지했다.

## 과거 통합 시험 기록

아래 시험은 해당 시점의 구성과 범위를 설명하며 현재 Pi 운영 설정을 뜻하지 않는다.

### MQTT 통합 시험의 흐름

2026-11-17 Pi ARM64의 실제 MN-CSE와 Mosquitto에서 확인했다. 모든 기록은 운영과 분리된 시험 CNT에 썼고, radar와 Vision CIN은 모의 데이터였다. 시험 전용 ACP로 RiskEngine의 fusedTracks 조회 권한을 확인했으며, alert 알림은 ESP가 아닌 MQTT 관찰 구독자로 받았다.

```mermaid
sequenceDiagram
  participant P as 모의 radar 발행기
  participant V as 모의 Vision CIN 발행기
  participant B as Pi Mosquitto
  participant C as Pi MN-CSE TinyIoT-MN
  participant R as RiskEngine 시험 프로세스
  participant O as MQTT alert 관찰 구독자
  V->>C: HTTP POST 모의 fusedTracks CIN
  P->>B: MQTT oneM2M radar CIN 요청
  B->>C: 시험 radar CIN 생성
  C->>B: radar SUB notification
  B->>R: m2m:sgn 알림
  R->>R: 거리 · CPA 판정
  opt 레이더 판정이 SAFE
    R->>C: HTTP GET 최신 fusedTracks/la
    C-->>R: 모의 Vision CIN
    R->>R: camera_only + raise면 WARNING으로 상향
  end
  R->>B: MQTT events 및 alert CIN 요청
  B->>C: 두 시험 CNT에 CIN 생성
  C-->>R: rsc=2001 응답
  C->>B: alert SUB notification
  B-->>O: 시험 경보 MQTT 수신
  Note over R,O: 실제 작업자 ESP·LED·부저는 연결하지 않음
```

시험 결과는 SAFE + 신선한 `camera_only + raise` → WARNING, 신선한 raise 없음 → SAFE, CPA WARNING(`t_cpa_s=2.5936`, `d_cpa_m=0`) → CPA DANGER(`t_cpa_s=0.9113`, `d_cpa_m=0`), 입력 만료 → UNKNOWN이다. `events`와 `alert` 생성 응답은 `rsc=2001`이었고, 별도 관찰 구독자가 alert MQTT 알림을 받았다. alert의 기존 `ttc` 필드는 `null`이며 CPA 값은 `events`에 기록된다. 실제 LD2450 업로더, VisionAI 실제 출력, 작업자 ESP와 부저, 운영 ACP는 미검증이다. 사용한 tinyIoT는 SUB 검증 알림에 수신 애플리케이션 응답이 없는데도 SUB를 생성했다. **검증 응답 구현과 다른 tinyIoT 버전의 호환성은 미확인**이다.

### RiskEngine MVP의 HTTP 입출력

```mermaid
sequenceDiagram
  participant C as MN-CSE
  participant R as main 기본 HTTP RiskEngine MVP
  R->>C: HTTP GET radar/la (polling)
  C-->>R: CIN 또는 오류
  R->>R: 거리 · CPA 또는 UNKNOWN
  R->>C: 상태 변경 시 HTTP POST events CIN
  Note over R,C: 별도 Draft PR 작업본은 MQTT 입력·출력과 SAFE 시 Vision HTTP GET을 추가
```

### 별도 장치 경보 경로

`main`의 레이더 업로더는 `LOCAL_DECISION=True`일 때 `AE-forklift01/alert`에 임시 경보를 기록한다. RiskEngine MVP의 출력은 `events`다. MN-CSE가 alert 구독을 통해 작업자 단말로 보내는 HTTP·MQTT 수신 코드와 SUB 스크립트가 있다. 실제 설치 펌웨어, 구독 설정, CIN 수신 및 LED·부저 동작을 각각 확인한다. HTTP 구현은 파싱 전에 응답을 보내므로 LED와 부저는 장치에서 별도로 확인한다.

## 리소스와 책임

```text
<TinyIoT-MN>                              # 팀 제안; 실제 서비스별 응답 확인
├─ AE-forklift01 (Cforklift01)
│  ├─ radar       [CNT]                   # radar CIN
│  └─ alert       [CNT]                   # 장치용 경고; 작성 주체·정책 확인
├─ AE-riskengine (Criskengine)
│  └─ events      [CNT]                   # 위험 판단 이력
├─ AE-VisionAI (CVisionAI)
│  └─ fusedTracks [CNT]                   # Vision 융합 결과
├─ AE-zonealarm01
│  └─ alert       [CNT]                   # 목표·실제 연결 미검증
└─ AE-camera01
   └─ detect      [CNT]                   # 기존 구상; Vision 경로와 역할 확인
```

`radar`에는 대상이 최대 3개인 CIN을 저장한다. 현재 `main`의 RiskEngine MVP는 `events`를 작성하고 별도 `alert`는 작성하지 않지만, #14를 기반으로 한 이 엔진 Draft PR은 시험용 alert CNT 기록과 MQTT SUB 알림을 확인했다. 현재 `main`의 레이더 업로더는 `LOCAL_DECISION=True`가 기본이다. 실제 작업자 경보 경로로 전환하기 전까지 운영 alert CNT의 작성자는 한 번에 하나로 유지한다.

Vision은 `AE-VisionAI/fusedTracks`에 결과를 기록하는 코드가 있다. 이 엔진 Draft PR은 레이더 판정이 SAFE일 때 최신 fusedTracks CIN을 HTTP GET하고, 신선한 `cam_ok=true` 결과의 `camera_only + raise`만 WARNING으로 올리는 규칙을 구현·모의 Vision CIN으로 시험했다. 실제 VisionAI 생산자 연결과 작업자 식별 매핑은 미검증이다. Vision의 `ghost_suspect`를 사람 부재의 확정으로 취급하지 않는다.

## 통신과 시험 결과

| 구간 | 확인된 내용 | 남은 확인 |
|---|---|---|
| LD2450 → Pi | UART 직접 연결은 현태의 설명. 실제 현장 전체 연결 시험으로 확대 해석하지 않는다. | 실제 배선·작동 중 업로더 버전·CIN 연속 기록 |
| radar → MN | `main`의 Pi 업로더는 기본 MQTT로 발행하며 유효한 빈 프레임도 업로드를 시도한다. MQTT 생성·HTTP 조회의 Pi 시험은 팀 보고다. | 실제 설치 버전, MQTT 응답, 빈 CIN 도착과 전송 주기 |
| radar → RiskEngine → events | Pi ARM64의 실제 MN-CSE·Mosquitto와 별도 CNT에서 모의 radar CIN → MQTT SUB 알림 → 거리·CPA 판정 → MQTT events CIN을 시험했다. 생성 응답 `rsc=2001`과 CIN 조회를 확인했다. | LD2450 업로더에서 생성한 실제 CIN·연속 전송, 실제 입력 주기와 stale 설정 |
| MQTT notification → RiskEngine → events | PR #14의 MQTT 입력·events 작업본을 기반으로 Pi 시험을 다시 했다. SUB 알림 처리와 MQTT events 생성 응답·저장을 확인했다. | 표준 SUB 검증 응답, 재접속·복구 및 다른 tinyIoT 버전 호환 |
| Vision | PR #9·#21은 Vision 입력과 MQTT radar 입력을 다룬다. RiskEngine은 Pi의 별도 CNT에 넣은 모의 fusedTracks를 SAFE 판정 때 HTTP GET했다. `camera_only + raise`의 WARNING 상향과 raise 없는 SAFE 유지를 확인했다. | VisionAI 실제 fusedTracks 생성·신선도·표적 연결을 RiskEngine에 연동 |
| MN ↔ IN | Pi MN과 노트북 IN의 CSE 연결 성공이 보고됐다. 별도 Pi 내부 IN 시험도 보고됐다. | 어떤 서버·이름·ID인지와 등록, 원격 조회, 실제 `events` 전달을 각각 검증 |
| MN/IN → 관제 | 대시보드는 기본 MN 최신 CIN 조회와 선택적 IN 접속 확인을 구현한다. 가짜 CSE 기반 단위 테스트 4개를 확인했다. | 실제 Pi 데이터 조회, IN을 통한 관제 데이터 조회 |
| MEC 서비스 발견 및 가용성 | PR #16 모의 Vision discovery 시험, 2026-11-20 Pi에서 MEC011 발견 → MN-CSE fusedTracks/la 조회 → 시험 상태 CIN 기록을 확인했다. | 실제 Vision 앱의 서비스 등록, 상시 IPE 설정, RiskEngine의 IPE 상태 소비, 자동 MEC 등록 상태 갱신 및 장시간 동시 부하 |
| alert → ESP | RiskEngine의 MQTT alert CIN을 Pi 시험 CNT에 기록하고, MQTT 관찰 구독자가 SUB 알림을 받았다. | 설치 펌웨어의 SUB/nu, 실제 ESP CIN 수신, LED·부저 동작 및 운영 ACP |

상희의 MQTT 시험 보고는 RAM에 둔 DB 복사본에서 330건 중 325건의 생성 성공 응답을 확인했다. 5건의 실패 또는 응답 누락 원인은 미확인이다. 같은 보고의 SD카드 DB 약 1.6초/건은 별도 환경의 관찰이며 일반적인 지연 또는 성능 보장값이 아니다. 1초 데이터 만료 기준과 실제 CIN 수신 간격은 재측정이 필요하다.

## 좌표·시간과 위험 판단

- radar CIN의 x·y는 mm, v는 cm/s라는 코드·시험 가정이 있다. `slot`을 포함하는 실제 CIN 예시가 보고됐지만, 다중 표적 교차·가림·소실 시 슬롯 유지와 재사용은 미검증이다.
- Vision의 fusedTracks x·y·`dist_m`은 m, `ttc_s`는 초라는 현재 코드 가정이다. 실제 설치 시 센서의 원점·축 방향·보정과 시간 기준을 확인한다.
- RiskEngine은 현재 거리와 같은 표적으로 연결한 연속 좌표의 변화로 상대속도·2D CPA를 계산한다. `t_cpa`는 최근접 시각이지 위험 반경에 처음 들어가는 시각이 아니며, 현재 속도 유지 조건의 예측이다. Vision의 거리/접근속도 `ttc_s`와 동일시하지 않는다.
- 위험 반경·거리·시간 임계값은 시험 가설이다. 센서 오차, 회전하는 레이더 좌표계, 센서 설치 오프셋 및 지게차 실제 크기는 추가 검토가 필요하다.
- 기존 GitHub MVP는 시작 시 오래된 `radar/la`를 새 입력으로 받아들일 수 있다. 별도 엔진 작업본은 첫 CIN을 기준점으로 기억하고 다음 CIN을 기다린다. 현재 Pi 업로더는 유효한 빈 프레임도 전송을 시도한다. 실제 MN에 빈 CIN이 계속 도착하는지, 프레임 중단 시 UNKNOWN으로 전환하는지 확인한다.

## 실패와 장애 처리

| 상황 | 현재 확인 및 미결 사항 |
|---|---|
| 입력 누락·오래된 CIN | 엔진의 기존 stale 정책은 UNKNOWN이다. 최근 별도 작업본의 최초 CIN 보류 정책은 실제 장비 미검증. |
| MN → IN 연결 실패 | 기존 MN 코드에는 시작 시 IN 등록 실패로 부팅이 중단되는 경로가 있다. IN 장애 중 MEC 로컬 기능 유지와 재연결은 팀 논의 중이다. 독립 시험에서는 등록을 생략했으므로 이 정책을 검증하지 않았다. |
| 통지 확인·재전송 | MQTT 시험 tinyIoT는 직접 `m2m:sgn` 형태의 검증 알림을 발행했고 별도 수신 응답 없이 SUB를 생성했다. 표준적인 검증 응답 처리, 중복·유실·재연결은 추가 검증이 필요하다. |
| 이벤트 저장 지연·timeout | 응답 timeout 뒤에도 CIN이 생성된 사례가 있다. 중복 방지와 저장 여부 확인, 재처리 정책이 필요하다. |
| MEC 서비스 장애 | 등록 상태와 실제 API 응답·입력 신선도를 각각 확인한다. Vision 중단 시 신선한 레이더로 판단을 유지하는 목표 동작과 상태 전달은 실장비 미검증이다. |
| RiskEngine·Pi·Wi-Fi 장애 | 엔진이 멈추면 새 판정을 기록할 수 없다. 장치 측 무신호 동작, 별도 인터락, 통신 복구 및 재가동은 미확정이다. |

`LOCAL_DECISION`은 레이더 노드의 임시 alert 작성 로직이며, 네트워크에 의존하지 않는 직접 모터 정지 인터락의 구현·검증 근거가 아니다. 기존 ESP 펌웨어의 `warn`/`danger` 이외 표시 및 부팅 시 LED 동작도 합의된 안전 정책이 아니다.

## 우선 확인할 인터페이스

1. 현태·태양: 실제 UART 업로더의 코드 버전, CIN `slot`·좌표·속도·timestamp, 빈 프레임 전송 주기, alert 작성 주체 확인.
2. 광민·태양: 실제 서비스의 CSEBase `rn`/`ri`/`csi`, 서버·DB, MQTT 토픽·oneM2M 응답·ACP, IN 등록과 이력 전달 분리 검증.
3. 상희·태양: 실제 fusedTracks CIN의 단위·원점·축·ID·신선도 및 판정 반영 여부 확인. slot이 없을 때 Vision과 엔진의 대체 ID 규칙은 현재 차이가 있다.
4. 팀 공통: UNKNOWN, 장치 경고, 연결 장애·복구, 로컬 인터락과 재가동의 기준을 결정하고 실제 장비에서 검증.

## 근거와 기록

- [프로젝트 README](../README.md): 기존 구상, 현재 UART 배선 표와 목표 배선.
- [RiskEngine README](../engine/README.md) 및 [RiskEngine 코드](../engine/risk_engine.py): 현재 저장소 MVP의 거리·CPA와 전제.
- [Vision 코드](../vision/src/vision4iot/main.py), [Vision 설계](../vision/CLAUDE.md), [Vision PR #9](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/9): Vision 입출력과 시험 보고.
- [CSE 명명안](cse-naming.md): 제안 이름과 전환 시 고려사항.
- [이슈 #7](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/issues/7), [이슈 #8](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/issues/8): 독립 MN 및 Vision 모의 연동 기록. 각 이슈의 시점과 환경에 한정한다.
- 현태·광민의 배선 및 서버 시험 설명은 팀 전달 내용이다. 코드 존재, 담당자 보고와 독립적인 실장비 재현 결과를 구별한다.
