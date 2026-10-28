# Sejong_4IoT_OneM2M

**중장비 근접 위험 감지 및 자동 정지 시스템**
oneM2M · ETSI MEC 기반 AIoT 해커톤 · 4IoT 팀

> 최종 수정: 2026-10-28

---

## 1. 프로젝트 개요

### 1.1 배경

지게차와 크레인은 차체 구조상 사각지대가 넓어, 후진이나 선회 중 작업자와 부딪히거나 끼이는 사고가 반복된다. 기존 후방카메라와 경광등은 운전자를 보조할 뿐 작업자에게 직접 경고하지 않고, 장비가 스스로 멈추지도 않는다. UWB·BLE 태그 방식은 작업자가 장비를 착용해야 해서, 미착용이나 배터리 방전 시 보호 공백이 생긴다.

### 1.2 목표

| 목표 | 내용 |
|---|---|
| 무태그 감지 | 24GHz mmWave 레이더(HLK-LD2450)로 작업자를 착용 장비 없이 감지한다 |
| 예측형 판단 | 충돌까지 남은 시간(TTC)으로 위험도를 판정해 장비 자동 감속·정지와 작업자 경보를 수행한다 |
| 표준 상호운용성 | 모든 데이터를 oneM2M 표준 리소스로 관리해 관제·분석과 타사 장비 연동이 가능하게 한다 |

### 1.3 핵심 차별점

| 항목 | 내용 |
|---|---|
| 무태그 감지 | 작업자 착용 장비가 필요 없어 미착용 공백이 없다 |
| 예측형 판단 | 거리와 접근 속도로 TTC를 계산한다. 빠르게 다가오면 먼 거리에서도 경보한다 |
| 3중 경보 계층 | 로컬 인터락 → MEC 판단 → 클라우드 분석. 네트워크 장애 시에도 정지한다 |
| Fail-safe | 통신·전원 이상 시 기본 동작이 '정지'다 |
| 표준 연동 | oneM2M 리소스·구독 구조로 다른 장비와 관제 시스템이 같은 방식으로 데이터를 받는다 |

---

## 2. 시스템 구성

```mermaid
flowchart TB
  subgraph FIELD["현장 (지게차 모형 · 고정형)"]
    RADAR["레이더 노드<br/>ESP8266 #1 + LD2450"]
    ACT["장비 동작부<br/>Arduino · 모터 · LED"]
    ALARM["작업자 경보기<br/>ESP8266 #2 · 부저"]
    CAM["카메라 노드<br/>웹캠 · OpenCV"]
  end

  subgraph MEC["MEC 서버 (Raspberry Pi 4B)"]
    CSE["MN-CSE<br/>tinyIoT"]
    ENGINE["위험 판단 엔진<br/>거리 · TTC"]
    AI["AI 추론<br/>궤적 예측 · 핫스팟"]
  end

  subgraph CLOUD["클라우드 (노트북 또는 대회 플랫폼)"]
    IN["IN-CSE<br/>이력 · 통계"]
    DASH["관제 대시보드<br/>위험 지도 · 알림"]
  end

  RADAR -->|radar 데이터| CSE
  CAM -->|detect 데이터| CSE
  CSE <--> ENGINE
  CSE <--> AI
  CSE -->|forklift01/alert 알림| RADAR
  CSE -->|zonealarm01/alert 알림| ALARM
  RADAR -.->|RUN·WARN 신호 / 로컬 인터락| ACT
  CSE --> IN --> DASH
```

| 계층 | 구성 | 역할 |
|---|---|---|
| 현장 | 레이더 노드 (ESP8266 #1 + LD2450) | 표적 좌표·속도 수집, 로컬 인터락 판정, CSE 업로드 |
| 현장 | 장비 동작부 (Arduino + 모터 + LED) | 장비 동력 표현, 상태별 감속·정지·표시 |
| 현장 | 작업자 경보기 (ESP8266 #2 + 부저) | 작업 구역 내 작업자 경보 |
| 현장 | 카메라 노드 (웹캠) | 움직임·사람 검출로 레이더 감지 보완 |
| MEC | Raspberry Pi 4B | MN-CSE(tinyIoT), 위험 판단 엔진, AI 추론 |
| 클라우드 | 노트북 또는 대회 제공 플랫폼 | IN-CSE, 이력 저장, 관제 대시보드 |

대회에서 MEC 플랫폼을 제공하면 위험 판단 엔진과 AI를 MEC 애플리케이션으로 배포한다.

### oneM2M 서버로 tinyIoT를 선택한 이유

초기 기획은 Mobius였으나 tinyIoT로 변경했다. tinyIoT는 C로 작성된 경량 oneM2M CSE라 라즈베리파이에서 부담 없이 동작하고, ETSI MEC 샌드박스에도 MN-CSE로 포함되어 있어 oneM2M과 ETSI MEC를 함께 다루는 대회 조건에 맞는다.

---

## 3. 동작 원리

### 3.1 감지

LD2450을 지게차 모형 후방(후진 사각지대 방향)에 고정한다. 최대 3명을 동시에 추적하며 표적별 x·y 좌표(mm)와 속도(cm/s)를 출력한다(탐지 약 6m, 시야각 ±60°).

### 3.2 위험 판단

```mermaid
flowchart LR
  A["입력 수집<br/>x · y · 속도 (최대 3명)"] --> B["TTC 계산<br/>거리 ÷ 접근속도"] --> C["위험 구역 판정<br/>거리 · TTC 임계값"]
  C --> S["안전<br/>정상 가동"]
  C --> W["주의 · 감속 + 경보<br/>거리 3m 미만 또는 TTC 3초 미만"]
  C --> D["위험 · 즉시 정지<br/>거리 1.5m 미만 또는 TTC 1.5초 미만"]
```

TTC는 접근 중인 표적에 대해서만 계산한다. 레이더 노드는 거리 1m 미만을 감지하면 네트워크를 거치지 않고 바로 정지 신호를 낸다(로컬 인터락). 임계값은 초기값이며 시험 후 조정한다.

### 3.3 상태별 동작

| 상태 | 모터 | LED | 작업자 경보기 |
|---|---|---|---|
| 안전 | 정상 회전 | 초록 | 없음 |
| 주의 | 감속 (PWM 50%) | 노랑 점멸 | 부저 단속음 |
| 위험 | 정지 | 빨강 | 부저 연속음 |
| 복귀 | 안전 상태 3초 유지 후 재가동 | 초록 | 없음 |

### 3.4 3중 경보 계층

| 계층 | 위치 | 판단 기준 | 특징 |
|---|---|---|---|
| 1차 | 레이더 노드 | 거리 | 네트워크와 무관, 지연 최소 |
| 2차 | MEC (라즈베리파이) | TTC · 다중 표적 · AI 예측 | 구독 알림으로 동작부·경보기 제어 |
| 3차 | 클라우드 IN-CSE | 누적 이력 | 아차사고 통계, 핫스팟 분석 |

### 3.5 AI 적용

궤적 예측은 표적 이력으로 1~2초 뒤 위치를 예측하고 그 위치 기준으로 TTC를 보정한다. 핫스팟 분석은 누적된 위험 이벤트 좌표를 군집화해 상습 위험 구역을 찾아 대시보드에 표시한다.

---

## 4. oneM2M 리소스 설계

### 4.1 리소스 트리

```text
TinyIoT                         [CSEBase]  MN-CSE (라즈베리파이)
├─ defaultACP                   [ACP]      기본 접근 권한 정책 (자동 생성)
├─ AE-forklift01                [AE]       지게차      Origin: Cforklift01
│   ├─ radar                    [CNT]      표적 x·y·속도 (최대 3명), mni 100
│   └─ alert                    [CNT]      위험 상태 → 감속·정지, mni 20
│       └─ sub-alert-node       [SUB]      새 데이터 → 레이더 노드(ESP8266)에 알림
├─ AE-zonealarm01               [AE]       구역 경보기  Origin: Czonealarm01
│   └─ alert                    [CNT]      부저 동작, mni 20
├─ AE-riskengine                [AE]       위험 판단 엔진  Origin: Criskengine
│   └─ events                   [CNT]      위험 이벤트 (→ IN-CSE), mni 100
└─ AE-camera01                  [AE]       카메라      Origin: Ccamera01
    └─ detect                   [CNT]      움직임·사람 검출 결과, mni 100
```

| ty | 리소스 | 역할 |
|---|---|---|
| 5 | CSEBase | 서버 최상위 |
| 1 | ACP | 접근 권한 정책 |
| 2 | AE | 등록된 앱·장치 |
| 3 | CNT | 데이터를 담는 컨테이너 |
| 4 | CIN | 컨테이너에 쌓이는 데이터 한 건 |
| 23 | SUB | 구독 (변경 시 알림) |

`mni`(최대 인스턴스 수)를 설정해 오래된 데이터는 자동 삭제되고, 레이더는 표적이 있을 때만 업로드해 데이터가 과도하게 쌓이지 않게 한다.

### 4.2 구독 흐름

| 구독 대상 | 알림 받는 쪽 | 용도 | 상태 |
|---|---|---|---|
| AE-forklift01/radar | 위험 판단 엔진 | 레이더 데이터로 위험 판정 | 예정 |
| AE-forklift01/alert | 레이더 노드 (ESP8266) | 감속·정지 신호 출력 | 구현 |
| AE-zonealarm01/alert | 작업자 경보기 (ESP8266 #2) | 부저 동작 | 예정 |

### 4.3 데이터 형식 (con)

| 컨테이너 | 작성 | 형식 예시 |
|---|---|---|
| AE-forklift01/radar | 레이더 | `{"ts": 1760360000.12, "targets": [{"x": 373, "y": 366, "v": -8}]}` |
| AE-camera01/detect | 카메라 | `{"ts": 1760360000.15, "objects": [{"cls": "motion", "bbox": [120, 80, 60, 150]}]}` |
| AE-forklift01/alert | 엔진 | `{"level": "danger", "dist": 1200, "ttc": 1.2}` |
| AE-riskengine/events | 엔진 | `{"ts": 1760360000.12, "level": "danger", "target": 0}` |

`ts`는 Unix 시간(초, 소수점 포함), 거리는 mm, 속도는 cm/s, `level`은 `safe`, `warn`, `danger` 중 하나다. 레이더와 카메라 데이터를 시간으로 짝지을 수 있도록 모든 장치는 인터넷 시간 동기화를 켠다.

### 4.4 통신 바인딩

| 구간 | 방식 | 비고 |
|---|---|---|
| 디바이스 ↔ CSE | 현재 HTTP, 이후 MQTT | 설계상 MQTT 바인딩(브로커: Mosquitto). 우선 HTTP로 구독·알림 흐름을 완성한 뒤 전환 |
| CSE ↔ CSE | HTTP | MN-CSE(라즈베리파이) ↔ IN-CSE(클라우드) |

---

## 5. 저장소 구조

```text
Sejong_4IoT_OneM2M/
├─ README.md                    프로젝트 소개 (이 문서)
├─ .gitignore
├─ docs/
│  ├─ architecture.md           시스템 구성, 리소스 트리 상세
│  ├─ data-format.md            컨테이너별 데이터 형식 (팀 합의 문서)
│  └─ runbook.md                작업 재개 절차 (핫스팟 연결 → tinyIoT 실행)
├─ onem2m/
│  ├─ setup_onem2m.sh           AE·CNT 일괄 생성
│  ├─ sub_alert_node.sh         ESP8266 알림 구독 생성
│  └─ demo.sh                   시연용 조회·기록 스크립트
├─ radar/                       레이더 파트
│  ├─ README.md
│  ├─ ld2450.py                 LD2450 프레임 파싱 테스트
│  ├─ proximity.py              (초기 버전) 근접 경고 → ESP8266 직접 호출
│  └─ radar_node.py             레이더 데이터·위험 상태를 tinyIoT에 업로드
├─ camera/                      카메라 파트
│  ├─ README.md
│  └─ motion_detect.py          웹캠 모션 감지 → AE-camera01/detect
├─ engine/                      위험 판단 엔진 (TTC, 2단계 판정)
│  └─ README.md
└─ esp8266/
   ├─ led_server/               (초기 버전) /on·/off 웹서버
   │  ├─ led_server.ino
   │  └─ secrets.example.h
   └─ alert_node/               tinyIoT 구독 알림 수신 → 출력 제어
      ├─ alert_node.ino
      └─ secrets.example.h
```

Wi-Fi 정보가 들어가는 `secrets.h`는 `.gitignore`로 제외하고, 양식인 `secrets.example.h`만 올린다.

---

## 6. 하드웨어 및 개발 환경

### 6.1 장비

| 장비 | 수량 | 용도 |
|---|---|---|
| HLK-LD2450 24GHz 레이더 | 1 | 작업자 무태그 감지 |
| ESP8266 (NodeMCU) | 2 | #1 레이더 노드, #2 작업자 경보기 |
| Arduino | 1 | 장비 동작부 제어 (모터·LED·부저) |
| Raspberry Pi 4B | 1 | MEC 서버 (tinyIoT, 엔진, AI) |
| 모터 + 모터 드라이버 (L298N/L9110S) | 1 | 장비 동력 표현, 속도·방향 제어 |
| LED (R/Y/G) + 220Ω 저항 | 각 1 | 상태 표시 |
| 부저 | 2 | 동작부, 경보기 (구매 필요) |
| 10kΩ 저항 | 1 | RUN 신호 풀다운 (Fail-safe) |
| 웹캠 | 1 | 카메라 노드 |
| 3D 프린터 | 1 | 지게차 모형, 레이더 마운트, 케이스 |
| 노트북 | 1 | IN-CSE, 대시보드 |

### 6.2 소프트웨어

| 구분 | 내용 |
|---|---|
| MEC OS | Raspberry Pi OS Lite 64-bit (Debian Trixie) |
| oneM2M CSE | tinyIoT (C, DB는 SQLite) |
| 레이더·엔진 | Python 3, pyserial |
| ESP8266 | Arduino IDE, esp8266 보드 패키지, ArduinoJson |
| 카메라 | Python 3, OpenCV |
| 개발 도구 | VS Code Remote-SSH, Git/GitHub |

### 6.3 배선

**현재 프로토타입 (LD2450 → 라즈베리파이 UART)**

| LD2450 | Raspberry Pi 4B |
|---|---|
| 5V | 핀 2 (5V) |
| GND | 핀 6 |
| TX | 핀 10 (GPIO15, RXD) |
| RX | 핀 8 (GPIO14, TXD) |

통신 규격은 256000bps, 8N1, 3.3V 레벨이다.

**최종 구성 (LD2450 → ESP8266 #1 → Arduino)**

| 연결 | 핀 | 비고 |
|---|---|---|
| LD2450 5V / GND | ESP8266 #1 VIN / GND | |
| LD2450 TX | ESP8266 #1 D7 (GPIO13) | `Serial.swap()` 후 하드웨어 RX |
| LD2450 RX | 미연결 | GPIO15 부팅 문제 회피 |
| ESP8266 #1 D5 | Arduino D2 | RUN 신호, 10kΩ 풀다운 → 선이 끊기면 정지 |
| ESP8266 #1 D6 | Arduino D3 | WARN 신호 |
| ESP8266 #1 GND | Arduino GND | 공통 접지 필수 |
| Arduino D5 / D7 / D8 | 모터 드라이버 ENA / IN1 / IN2 | D5 PWM으로 감속 |
| Arduino D9 | 부저 | |
| Arduino D10 / D11 / D12 | LED R / Y / G | 220Ω 직렬 |

ESP8266의 3.3V 출력은 5V Arduino 입력에서 대부분 HIGH로 인식된다. 불안정하면 레벨시프터를 추가한다.

---

## 7. 구현 방법

### 7.1 라즈베리파이 UART 설정

라즈베리파이 기본 mini UART는 256000bps에서 불안정하므로 블루투스를 끄고 PL011 UART를 쓴다.

```bash
sudo raspi-config        # Interface Options → Serial Port: 로그인 셸 No, 하드웨어 Yes
echo "dtoverlay=disable-bt" | sudo tee -a /boot/firmware/config.txt
sudo apt install -y python3-serial
sudo reboot
```

### 7.2 tinyIoT 설치

```bash
sudo apt install -y git build-essential openssl libssl-dev libwebsockets-dev libsqlite3-dev libpq-dev
git clone --recursive https://github.com/seslabSJU/tinyIoT.git
cd tinyIoT/source/server
```

`config.h`에서 두 가지를 바꾼다.

```c
#define SERVER_IP "라즈베리파이 IP"
#define DB_TYPE DB_SQLITE          // PostgreSQL 줄은 주석 처리
```

```bash
make clean && make
./server
```

`config.h`는 빌드할 때 프로그램에 포함되므로, IP를 바꾼 뒤에는 반드시 다시 빌드한다.

### 7.3 리소스 생성

```bash
bash onem2m/setup_onem2m.sh
```

### 7.4 레이더 노드 (radar/radar_node.py)

LD2450 프레임(30바이트)을 파싱해 표적이 있을 때만 0.5초 간격으로 `AE-forklift01/radar`에 올린다. 위험 판단 엔진이 완성되기 전까지는 `LOCAL_DECISION = True`로 두어, 가장 가까운 표적 거리로 임시 판정한 결과를 `AE-forklift01/alert`에 기록한다. 경보는 상태가 바뀔 때만 기록하고, 해제는 일정 시간 범위 밖에 있어야 하도록 지연을 둬 경계선 근처에서 깜빡이지 않게 한다.

```bash
python3 radar/radar_node.py
```

### 7.5 ESP8266 알림 노드 (esp8266/alert_node)

ESP8266은 `/notify` 주소로 tinyIoT의 알림을 받아 `con`의 `level`이 `warn`이나 `danger`이면 출력을 켠다. Arduino IDE에서 ArduinoJson 라이브러리를 설치하고, `secrets.h`에 Wi-Fi 정보를 넣은 뒤 업로드한다.

### 7.6 구독 생성

```bash
bash onem2m/sub_alert_node.sh <ESP8266_IP>
```

구독은 ESP8266이 아니라 라즈베리파이에서 만든다. tinyIoT는 구독을 만들 때 알림 대상에게 확인 요청을 먼저 보내는데, ESP8266이 직접 구독을 요청하면 응답을 기다리는 동안 그 확인 요청에 답할 수 없어 생성이 실패하기 때문이다.

### 7.7 동작 확인

```bash
bash onem2m/demo.sh
```

리소스 구조 조회, 경고 기록, 최신 값(`la`) 조회를 한 단계씩 실행한다.

### 7.8 네트워크 주의사항

시연과 개발은 휴대폰 핫스팟(2.4GHz, WPA2, 영문 SSID)을 사용한다. ESP8266은 2.4GHz와 WPA2만 지원하고, 공용 Wi-Fi는 기기 간 통신을 막는 경우가 많기 때문이다. 핫스팟은 연결할 때마다 IP가 바뀔 수 있으니 작업을 재개할 때는 `docs/runbook.md` 절차를 따른다.

---

## 8. 구현 단계 및 진행 현황

| 단계 | 내용 | 완료 기준 | 현황 |
|---|---|---|---|
| 1 | 레이더 단독 검증 | 3명 좌표·속도 수신, 정지한 사람 감지 확인 | 라즈베리파이 파싱 완료, 상세 검증 남음 |
| 2 | 동작부 + 로컬 인터락 | 1m 미만 시 정지, 신호선 분리 시 정지 | ESP8266 LED로 원격 동작 검증, 동작부 미착수 |
| 3 | oneM2M 연동 | AE·CNT 등록, radar cin 생성 | tinyIoT 설치 및 리소스 생성 완료 |
| 4 | 위험 판단 엔진 + 구독 알림 | 동작부·경보기 제어, 왕복 지연 측정 | 레이더 노드·ESP8266 구독 알림 구현, 시험 예정 |
| 5 | AI + IN-CSE·대시보드 | 이벤트·핫스팟 표시 | 예정 |
| 6 | 모형 완성 + 시연 리허설 | 시나리오 연속 10회 성공 | 예정 (3D 모형은 병행) |

현재 프로토타입은 책상 위 축소 시연을 위해 경고 거리를 50cm 한 단계로 두었다. 설계의 2단계 판정(3m, 1.5m)과 TTC는 위험 판단 엔진에서 구현한다.

### 레이더 남은 검증 항목

| 항목 | 방법 | 확인 목적 |
|---|---|---|
| 거리 정확도 | 줄자로 1~5m 지점에서 비교 | 경고 거리 설정의 신뢰성 |
| 탐지 각도 | 정면 기준 좌우 이동 | 설치 위치·방향 결정 |
| 다중 타겟 | 2~3명 동시 이동 | 가장 가까운 사람 누락 여부 |
| 장시간 정지 | 30초 이상 정지 | 위험 구역 내 정지자 소실 여부 |
| 금속 반사 | 금속 구조물 근처 측정 | 가짜 타겟에 의한 오경보 |
| 반응 속도 | 경계 진입부터 출력까지 | 경고 지연 시간 |

---

## 9. 팀 역할 및 협업 규칙

| 파트 | 담당 | 개발 환경 |
|---|---|---|
| 레이더 · ESP8266 노드 | 지현태 | 라즈베리파이 + LD2450 + ESP8266 |
| 카메라 실증 | 팀원 | 노트북 + 웹캠 (통합 시 같은 CSE에 연결) |
| 위험 판단 엔진 · AI · 대시보드 | 미정 | 노트북 (Ubuntu VM 또는 WSL2) |

| 규칙 | 내용 |
|---|---|
| 작업 범위 | 자기 파트 폴더만 수정한다 |
| 작업 순서 | 시작 전 `git pull` → 작업 → `add` / `commit` / `push` |
| 공용 파일 | `docs/data-format.md`와 `onem2m/`은 팀 합의 후 수정한다 |
| 커밋 메시지 | `[radar] 업로드 기능 추가`처럼 파트명을 앞에 붙인다 |
| 비밀 정보 | Wi-Fi 비밀번호, 계정 정보는 저장소에 올리지 않는다 |

파트끼리는 oneM2M 서버를 통해서만 데이터를 주고받으므로, 리소스 트리와 데이터 형식만 지키면 따로 개발한 코드도 CSE 주소만 바꿔 바로 합칠 수 있다. 코드에서 CSE 주소는 환경 변수 `CSE_URL`로 받는다.

---

## 10. 시연 시나리오 및 목표 지표

| 순서 | 상황 | 기대 동작 |
|---|---|---|
| 1 | 평상시 | 모터 회전, 초록 LED |
| 2 | 작업자 접근 (3m 이내) | 감속, 노랑 점멸, 경보기 부저 |
| 3 | 위험 구역 진입 (1.5m 이내) | 즉시 정지, 빨강 LED, 대시보드 이벤트 표시 |
| 4 | 이탈 | 안전 상태 3초 유지 후 자동 재가동 |
| 5 | 빠른 접근 | 먼 거리에서도 TTC로 조기 경보 (거리 기준 방식과 비교) |
| 6 | Fail-safe | Wi-Fi를 차단해도 로컬 인터락으로 정지 |

| 지표 | 목표 |
|---|---|
| MEC 경보 왕복 지연 | 200ms 이내 |
| 로컬 인터락 반응 | 2단계에서 측정 후 확정 |
| 시연 판정 | 반복 시연 중 미탐 0회 |

---

## 11. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| 정지한 사람의 감지 약화 | 1단계에서 검증, 마지막 위치를 일정 시간 유지하는 로직 추가 |
| 최대 3명 추적 한계 | 시연 인원 제한, 확장 시 다중 센서 |
| Wi-Fi 불안정 | 로컬 인터락과 Fail-safe로 대응, 시연은 핫스팟 사용 |
| 레이더 데이터 과다 | `mni` 설정, 표적이 있을 때만 업로드 |
| 3.3V ↔ 5V 신호 레벨 | 필요 시 레벨시프터 |
| 라즈베리파이 연산 부담 | 카메라 AI가 무거우면 노트북에서 처리해 같은 CSE에 업로드 |

## 12. 확장 계획

| 방향 | 내용 |
|---|---|
| 인프라 센서형 | 사각지대 코너에 레이더를 고정하고 NRF24L01로 장비에 직접 정지 신호 전송 |
| 보안 강화 | NRF24 무암호 통신의 위협을 HackRF로 시연하고 HMAC + 카운터 메시지 인증으로 대응 |
| 다중 장비 | 장비별 AE만 추가하면 확장 가능 (oneM2M 표준 구조) |

---

## 참고

### LD2450 데이터 프레임

| 구간 | 크기 | 내용 |
|---|---|---|
| 헤더 | 4바이트 | `AA FF 03 00` |
| 타겟 1~3 | 8바이트 × 3 | x(2), y(2), 속도(2), 거리 해상도(2), 리틀 엔디언 |
| 테일 | 2바이트 | `55 CC` |

좌표와 속도는 최상위 비트가 1이면 양수, 0이면 음수이고 나머지 15비트가 절댓값이다. 타겟이 없으면 해당 8바이트가 모두 0이다.

### 알려진 문제와 해결

| 증상 | 원인 | 해결 |
|---|---|---|
| tinyIoT 빌드 중 `libwebsockets.h` / `libpq-fe.h` 없음 | README에 없는 의존 패키지 | `libwebsockets-dev`, `libpq-dev` 설치 |
| tinyIoT 실행 직후 DB 에러로 종료 | 기본 DB가 PostgreSQL | `DB_TYPE`을 `DB_SQLITE`로 변경 후 재빌드 |
| 라즈베리파이 → ESP8266 요청 실패 | ESP8266 Wi-Fi 절전 모드 | `WiFi.mode(WIFI_STA)`, `WiFi.setSleepMode(WIFI_NONE_SLEEP)` |
| ESP8266이 핫스팟에 연결 안 됨 | 5GHz 또는 WPA3 설정 | 핫스팟을 2.4GHz, WPA2로 설정 |
| curl 명령 붙여넣기 오류 | 줄바꿈 손실 | 명령을 한 줄씩 실행하거나 스크립트 파일로 실행 |

### 링크

- tinyIoT: https://github.com/seslabSJU/tinyIoT
