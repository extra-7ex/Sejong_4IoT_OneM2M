# SafeZone 아키텍처와 통합 상태

## 2026-11-20 Pi 현장 확인과 장비 복구 후속 보고

상세 Pi 조회는 18:45 KST의 읽기 전용 스냅샷이고, 그 이후 장비를 복구한 결과는 작업자 보고로 추가했다. 서비스·리소스 관찰과 수동 Vision 실행은 시간상 서로 다른 상태다. 주소와 계정은 공개하지 않는다. 전체 재부팅 복구, Vision 상시 가용성, 장기 운용 및 안전 성능은 검증하지 않았다. 상세 기록은 [배포 및 운영 기록](deployment.md)을 참고한다.

```mermaid
flowchart LR
  LD["LD2450"] -->|"UART"| UP["Pi radar uploader"]
  UP -->|"MQTT: oneM2M CIN create"| MN["Pi tinyIoT MN-CSE"]
  MN --> RAD["AE-forklift01/radar CNT"]
  RAD -->|"HTTP GET /la · polling"| RE["RiskEngine<br/>별도 설치본"]
  CAM["Logitech C270"] --> VISION["VisionAI<br/>/home/user/vision4iot"]
  VISION -->|"HTTP: oneM2M CIN · manual run"| FUSED["AE-VisionAI/fusedTracks CNT"]
  FUSED -->|"HTTP GET latest CIN · polling"| RE
  RE -->|"HTTP CIN create"| EV["AE-riskengine/events CNT"]
  RE -->|"HTTP POST /fopt"| GRP["grp-safezone-alarms"]
  GRP --> FA["forklift alert CNT"]
  GRP --> WA["worker alert CNT"]
  GRP --> ZA["zone alert CNT"]
  FA -.->|"SUB: HTTP /notify"| E1["Forklift ESP"]
  WA -->|"SUB nu=Cworker01 → AE poa"| E2["Worker ESP<br/>DANGER risk mode observed"]
  EV -->|"HTTP polling · summary"| BR["MN→IN bridge"]
  BR -->|"HTTP"| IN["Laptop Docker IN-CSE"]
  MN --> DASH["Pi dashboard"]
  IN --> DASH
  MN --> IPE["MEC service-health IPE"]
  IPE -->|"HTTP GET Vision CIN / POST health"| MN
```

RiskEngine은 MQTT에서 레이더 알림을 구독하지 않는다. 업로더가 MQTT로 radar CIN을 만들고, 운영 엔진은 radar와 설정된 `fusedTracks/la`를 HTTP polling으로 읽는다. 판단 결과는 HTTP로 `events`에 쓰고 `/grp-safezone-alarms/fopt` 경보 그룹에 기록한다. 그룹에는 세 alert CNT의 현재 RI가 들어 있으며, worker AE 재등록 뒤 worker alert RI도 그룹에 다시 연결된 것을 확인했다. DANGER CIN은 세 alert CNT 모두에 기록됐고 작업자 ESP가 위험 모드에 진입했다. 두 ESP 보드가 동작하는 것도 확인됐지만, 현장 확인에서 명시적으로 관찰한 DANGER 출력은 작업자 ESP의 위험 모드다.

SUB 경로는 두 형태다. Forklift SUB는 HTTP `/notify` 주소를 직접 보유한다. Worker SUB는 `nu=Cworker01`을 사용하고, CSE가 작업자 AE의 `poa`로 주소를 확인한다. Worker AE를 다시 등록하면 alert CNT의 RI가 달라질 수 있으므로 그룹 `mid`도 현재 RI로 갱신해야 한다. 이번 점검에서는 갱신된 그룹 멤버십과 작업자 ESP의 위험 모드 진입을 확인했다.

현재 ACP 조회에서 radar 읽기, fusedTracks 읽기, alert 작성 권한이 구성된 것을 확인했다. Worker ACP는 `CAdmin`에도 create/retrieve/discovery 권한(마스크 35)을 부여한다. 이는 권한 구성이 존재한다는 확인이며, 최소 권한 보안 검토를 통과했다는 뜻은 아니다.

VisionAI는 C270에서 새 출력을 만들었고 `fusedTracks` CIN의 `cam_ok=true`를 확인했다. 당시 `tracks`는 비어 있어, 그 실행은 카메라 인식·출력 생성과 RiskEngine의 fresh 입력 경로를 확인한 것이며 사람 검출 성공 사례는 아니다. 뒤이은 Pi 조회 시에는 Vision 프로세스가 실행 중이지 않았고 최신 CIN은 약 13분 전이어서 엔진이 `vision=stale`로 판단했다. 즉, Vision 출력은 시험 중 fresh였으나 이번 점검 전체 시간 동안 계속 fresh였던 것은 아니다.

| 구성 | 후속 확인 | 범위와 한계 |
|---|---|---|
| Pi 프로세스 | MN-CSE, Mosquitto, radar uploader, polling RiskEngine, bridge, dashboard, MEC IPE 실행 중 | SSH/systemd를 읽어 확인. 재부팅 복구는 별도 미검증 |
| 위험 이벤트 | DANGER, WARNING, SAFE 이벤트 기록 및 HTTP 201 / RSC 2001 응답 관찰 | 임계값은 팀 시연 설정이며 안전 성능 인증이 아님 |
| 경보 경로 | 경보 그룹 현재 멤버 3개, 세 alert CNT 모두 DANGER, worker SUB/AE/그룹 RI 연결 | 작업자 ESP가 위험 모드 진입. 자동 지게차 정지는 확인하지 않음 |
| ESP | 두 ESP 보드 동작 확인 | 후속 복구 보고에서 worker ESP의 DANGER 위험 모드 관찰. 부저·서보의 모든 출력 조합은 확인하지 않음 |
| Vision | C270 인식, fresh CIN, RiskEngine에서 fresh 입력 확인 | 수동 실행 시 `tracks=[]`; 18:45 스냅샷은 실행 전 stale 상태. 상시 실행 미검증 |
| MEC/IPE | MEC 서비스 상태 IPE 실행 및 Vision 상태 자원 기록 경로 확인 | MEC 기여는 상태 가시성. 외부 MEC 플랫폼에서 추론 실행이나 지연 개선은 측정하지 않음 |
| IN·대시보드 | 브리지의 노트북 Docker IN 기록과 MN/IN 대시보드 연결 확인 | 브리지는 별도 HTTP 앱이며 직접 Mcc 동기화가 아님 |
| 시연 타이밍 | stale 입력 5초, target association 간격 5초 설정 확인 | 팀 데모 설정; 최적값·추적 정확도 검증 아님 |

### 18:45 이후 장비 복구 보고

worker AE 재등록으로 변경된 worker alert CNT RI를 현재 경보 그룹에 다시 연결했다. DANGER가 forklift·worker·zone alert CNT 각각에 기록되고 worker ESP가 위험 모드에 들어가는 것을 확인했다. 두 ESP 보드가 동작한다는 보고를 받았지만, 이 후속 보고에서 직접 관찰한 ESP 출력은 worker 위험 모드다. SG90 포크 서보와 부저의 실제 동작은 11월 15일·18일에 수행한 모형 시험 결과로 별도 취급한다.

C270은 Pi에서 인식됐다. VisionAI를 `/home/user/vision4iot` 실행 환경에서 수동 시작해 fresh `fusedTracks`를 만들고 RiskEngine이 이를 fresh로 읽는 것을 확인했다. 당시 `tracks`는 비어 있었다. 이는 카메라 입력과 전달 경로 확인이며 양성 사람 검출이나 systemd 상시 실행 확인은 아니다. 18:45 스냅샷의 stale Vision은 이 수동 실행 전 상태다.

Pi에도 IN-CSE 서비스가 있지만 브리지와 대시보드는 노트북 Docker IN-CSE를 사용한다. DHCP 주소 예약은 아직 구성하지 않았다. 아래 11월 17일 격리 시험은 모의 입력과 시험 CNT를 사용한 별도 기록이며 운영 장치 검증과 혼합하지 않는다.

## 문서 범위

팀 공유 정보, GitHub 코드와 별도 시험 결과를 정리한다. 아래의 설계·격리 시험 기록은 재연결 전의 구현·논의와 2026-11-17 시험을 보존하며, 최신 실장비 상태를 요약하는 부분은 문서 맨 위의 2026-11-20 후속 확인이다. **실장비 관찰**, **코드·모의 시험**, **미검증 목표**는 서로 다르다. 각 시험의 서버·DB와 데이터 출처를 확인하고, 단일 시험 결과로 실제 장비 전체 연동이나 산업안전 성능을 주장하지 않는다.

- 저장소 기준: [Draft PR #14](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/14)는 RiskEngine MQTT radar 알림 입력과 `events` 기록의 기반이다. 이 문서의 Pi 검증과 `alert`·Vision 조언 코드 변경은 별도 Draft PR로 제안하며, #14나 `main`에 직접 푸시하지 않는다.
- [Vision MQTT 입력 PR #21](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/21)은 VisionAI가 레이더 알림을 받는 경로다. RiskEngine의 fusedTracks 접근은 아래 Pi 시험에서 별도로 검증한 HTTP GET이며, #21의 레이더 입력 경로와 혼동하지 않는다.
- MEC 작업은 [실험 PR #16](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/16), [연동 AE PR #18](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/18), [Pi MN 시험 PR #19](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/19)에서 이어진다. 각각의 테스트 범위와 미검증 항목은 해당 PR에 한정한다.
- 현태의 설명: LD2450은 Pi UART에 직접 연결되어 있으며 ESP8266은 레이더와 직접 연결하지 않고 tinyIoT의 HTTP 알림을 받는다. 장비별 현재 펌웨어·동작은 재확인이 필요하다.
- 광민의 보고: Pi MN과 노트북 IN의 연결 시험 성공. 다른 시험에서는 Pi 내부 IN도 사용했다. CSE 등록과 `events`의 IN 전달은 별도 검증이다.
- [Vision PR #9](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/9): 실제 radar CIN 예시를 Vision이 읽었고, MQTT·HTTP 입력/출력과 녹화 영상으로 시험했다고 보고했다. PR은 작성 당시 열린 상태였으며 해당 보고의 전체 재현 여부는 별도 기록한다.

## 이전 통합 기록과 목표 구성

### 2026-11-17 기준의 이전 구현 기록

```mermaid
flowchart LR
  LD["LD2450 레이더"] -- "UART 프레임<br/>256000 bps, 팀 설명" --> UP["Pi 레이더 업로더"]
  UP -. "radar CIN 생성<br/>실행 버전·방식 확인 필요" .-> RAD["tinyIoT MN-CSE<br/>radar CNT"]
  RAD -. "모의 radar CIN · Pi MN에서 MQTT 알림" .-> ENGINE["RiskEngine<br/>거리 · 2D CPA"]
  ENGINE -. "MQTT events CIN<br/>Pi 시험 CNT" .-> EVENT["events CNT"]
  CAM["카메라"] -. "녹화 영상 시험<br/>C270 실시간 미검증" .-> VISION["Vision AI"]
  RAD -. "HTTP polling 코드·시험 보고<br/>PR #21은 MQTT radar 입력" .-> VISION
  VISION -. "fusedTracks CIN<br/>시험 보고" .-> FUSED["fusedTracks CNT"]
  ENGINE -. "HTTP GET latest fusedTracks/la<br/>radar SAFE일 때만 · Pi 시험" .-> FUSED
  FUSED -. "모의 Vision CIN 응답" .-> ENGINE
  ENGINE -. "MQTT alert CIN<br/>시험 CNT만" .-> TEST_ALERT["alert test CNT"]
  UP -. "LOCAL_DECISION 임시 alert 기록<br/>실행 버전 확인 필요" .-> ALERT["alert CNT"]
  ALERT -. "HTTP 또는 MQTT SUB 알림<br/>단말 통합 미검증" .-> ESP["ESP8266 경고 장치"]
  CSE["MN-CSE"] -. "등록 시험 보고<br/>데이터 전달 미검증" .-> IN["IN-CSE"]
```

점선은 특정 코드·시험 환경·목표 중 하나에 한정되며, 실제 전체 통합을 의미하지 않는다. `radar`, `events`, `fusedTracks`, `alert`는 MN-CSE 아래 CNT다. 현재 확인된 레이더 배선은 **LD2450 → Pi UART**다. ESP8266이 직접 radar를 읽는 구성은 과거 목표안이며 현재 배선으로 단정하지 않는다.

### 실제 호출 흐름과 MEC 목표 구조

아래 그림은 현재 확인된 oneM2M 호출 경로와 아직 구현·검증하지 않은 MEC011 연동 목표를 구분한다. LD2450은 oneM2M 장치가 아니며 Pi의 Radar Collection IPE/MN-AE에 UART로 연결된다. C270은 USB로 VisionAI에 연결된다. MEC service-health IPE는 VisionAI의 출력 상태만 읽고 camera stream을 처리하지 않는다.

```mermaid
flowchart LR
  LD["LD2450<br/>non-oneM2M device"] -->|"UART"| RAD["Radar Collection IPE<br/>MN-AE"]
  CAM["Logitech C270"] -->|"USB video"| VIS["VisionAI"]

  subgraph PI["Pi edge node · current deployment"]
    MN["tinyIoT MN-CSE<br/>MEC App role in reference architecture"]
    RAD -->|"Mca · MQTT radar CIN create"| MN
    VIS -->|"Mca · HTTP fusedTracks CIN create"| MN
    RR["AE-forklift01/radar"]
    VF["AE-VisionAI/fusedTracks"]
    EV["AE-riskengine/events"]
    GRP["grp-safezone-alarms<br/>/fopt"]
    FA["Forklift alert CNT"]
    WA["Worker alert CNT"]
    ZA["Zone alert CNT<br/>extension; no device"]
    MN --> RR
    MN --> VF
    MN --> EV
    MN --> GRP
    RE["RiskEngine<br/>separate install"]
    RR <-->|"Mca · HTTP GET polling"| RE
    VF <-->|"Mca · HTTP GET polling"| RE
    RE -->|"Mca · HTTP CIN create"| EV
    RE -->|"Mca · HTTP POST /fopt"| GRP
    GRP -->|"fopt fan-out · verified for three alert CNTs"| FA
    GRP --> WA
    GRP --> ZA
    IPE["Vision service-health IPE<br/>reads state only"]
    IPE -->|"Mca · GET fusedTracks health / POST status"| MN
    BR["MN→IN bridge AE"]
    MN <-->|"Mca · HTTP polling"| BR
    IN["Laptop Docker IN-CSE"]
    BR -->|"Mca · HTTP event summary create"| IN
    DASH["Dashboard"]
    DASH -->|"Mca · MN current state"| MN
    DASH -->|"Mca · IN event history"| IN
  end

  MEC["ETSI MEC Platform<br/>target integration"]
  MN -.->|"Mp1 · MEC011 service registration / discovery<br/>target; not live-verified"| MEC
  FE["Forklift ESP<br/>servo + buzzer"]
  WE["Worker ESP<br/>buzzer + LED"]
  FA -->|"Mca · SUB HTTP /notify<br/>fork/servo demo test"| FE
  WA -->|"Mca · SUB nu=Cworker01 → AE poa<br/>DANGER mode observed"| WE
  F["Fork actuator: SG90 servo<br/>on scale-model fork"]
  FE --> F
  KEY["Solid = deployed path or dated test<br/>Dotted = target / not verified"]
```

현재 RiskEngine은 MQTT radar notification을 구독하지 않는다. Radar Collection IPE가 MQTT로 CIN을 만들고, 별도 설치본 RiskEngine은 radar와 설정된 `fusedTracks/la`를 HTTP polling으로 읽어 `events`와 경보 그룹에 HTTP로 쓴다. 그룹 fan-out으로 세 alert CNT 모두에 DANGER가 기록됐고, 복구된 worker AE의 새 alert RI를 그룹에 다시 연결한 뒤 작업자 ESP가 위험 모드에 들어가는 것을 확인했다. Forklift ESP의 servo+buzzer 출력은 앞선 11월 15일·18일 모형 시험에서 보고됐으며, 이는 실제 차량의 주행 모터 제어가 아니다.

MN→IN 이력 이동은 브리지 AE가 MN을 HTTP polling하고 노트북 Docker IN에 HTTP로 생성 요청을 하는 두 Mca 구간이다. 직접 Mcc 동기화가 아니다. tinyIoT MN-CSE는 Pi의 edge 서비스다. 대회 참조 그림에서 이를 MEC App 역할로 대응해 표기했지만, 실제 ETSI MEC 플랫폼과의 Mp1/MEC011 서비스 등록·발견은 이 배치에서 연결하거나 검증하지 않았다. 실제 실행 중인 MEC 관련 기능은 Vision 출력의 신선도·카메라 상태를 읽어 oneM2M 상태 리소스로 기록하는 IPE다.

#### 등록 및 리소스 사전조건

- **MN-CSE**에 쓰거나 구독하는 AE는 등록 또는 기존 등록을 재사용하고, 해당 CNT와 접근 권한을 준비한다. MQTT radar 알림 시험과 작업자 경보 목표에는 각각 별도 SUB와 알림 수신 주소가 필요하다.
- **IN-CSE** 경유 관제를 구성하려면 MN-CSE 등록과 관제 AE의 조회 권한을 확인한다. 이벤트·상태를 IN에 보관할지, IN을 경유해 MN 리소스를 조회할지 결정하고 실제 조회로 검증한다.
- **MEC 플랫폼**에서 앱 배치·등록과 서비스 등록을 각각 확인한다. 레이더 수집과 VisionAI의 제공 서비스, 어댑터의 발견 권한과 실제 점검 대상은 별도로 정의한다. [ETSI GS MEC 011 §5](https://www.etsi.org/deliver/etsi_gs/MEC/001_099/011/03.03.01_60/gs_MEC011v030301p.pdf)

#### 관제 경로 확인

[main의 대시보드 서버](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/blob/e851fbf8ea7407f7614512da73b7fdf3dd30513d/dashboard/server.py)는 기본적으로 `DASH_CSE_BASE`의 `TinyIoT-MN`에서 `radar`, `events`, `fusedTracks`, `alert`의 최신 CIN을 읽는다. 선택 설정 `DASH_IN_BASE`는 CSEBase 접속 확인용이다. 서버는 기본 `CAdmin`으로 GET 요청을 보내며 자체 AE 등록을 수행하지 않는다. 브라우저는 대시보드 서버의 `/api/*`를 조회한다.

IN을 데이터 원본으로 쓰려면 선택한 전달 방식과 각 활성 조회 경로에서 실제 CIN을 읽을 수 있는지 확인해야 한다. 기본 서버는 네 가지 경로를 같은 `DASH_CSE_BASE`에 요청하므로 events 하나만 IN에 제공하면 나머지 경로의 데이터는 별도로 구성해야 한다. [대시보드 PR #12](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/12)의 시험 보고 범위는 가짜 CSE이며 실제 Pi 통합은 미확인이다.

#### MEC 가용성 확인 기준

| 확인 지점 | 확인할 내용 |
|---|---|
| 서비스 등록부 | 어댑터가 Mp1로 레이더 수집·Vision 서비스를 각각 발견하고 등록 상태를 읽는다. |
| 실제 입력 | 두 생산 앱을 하나씩 중단해 등록 상태와 실제 API 응답·최신 입력 시각을 각각 확인한다. 감지 주체, heartbeat/health check, 상태 갱신 방식은 미정이다. |
| RiskEngine 목표 동작 | Vision이 끊겨도 신선한 레이더가 있으면 레이더 판단을 유지한다. 레이더가 끊기거나 오래되면 UNKNOWN으로 처리한다. 유효한 빈 레이더 프레임은 정상 입력이다. |

[PR #16](https://github.com/extra-7ex/Sejong_4IoT_OneM2M/pull/16)의 격리 환경에서는 모의 Vision의 등록·발견·호출을 시험했다. 모의 서비스를 멈췄을 때 호출은 실패했지만 등록부에 ACTIVE가 남았다. 실제 장비에서 장애 감지 주체와 상태 전달 방식이 정해지면, 장애 감지 → 상태 기록 → 판정 전환을 별도 호출 흐름으로 기록한다.

아래 Pi 시험은 PR #14의 MQTT 입력·`events` 작업본을 기반으로 하며, 그 위에 `alert` 출력과 Vision 조언을 붙인 별도 Draft PR 변경을 사용했다. 여러 지게차 MN과 작업자 AE가 연결되는 구성은 확장 시나리오이며, 작업자와 레이더 표적의 매핑은 미정이다.

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
| MEC 서비스 발견 및 가용성 | PR #16에서 모의 Vision 등록·발견·호출을 시험했다. 중단 후 등록 상태는 ACTIVE로 남았다. | 실제 레이더·Vision의 장애 감지, 상태 CIN 기록과 판정 전환 |
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
