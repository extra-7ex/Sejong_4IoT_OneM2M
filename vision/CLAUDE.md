# 4iot VisionAI — 프로젝트 안내 (Claude Code용)

> 2026-11-07 제안: 운영 MN의 새 기본 이름은 `TinyIoT-MN`, CSE ID는 `/tinyiot-mn`이다. Pi 실제 적용은 미확인. 아래 과거 관찰·시험 서버 이름은 당시 값이다. [전환 안내](../docs/cse-naming.md).

이 폴더는 팀 4iot의 **영상·AI 파트(VisionAI)** 코드다. 담당: 상희.

**진행 방식:** 지금은 장비가 없어서 **노트북 + 웹캠으로 먼저 완성도 있게 구현**한다.
장비는 현태 → 광민(tinyIoT 작업) → 상희 순서로 넘어오며, 받으면 같은 코드를 **라즈베리파이 4 + Pi 카메라**로 옮긴다.
그래서 처음부터 "Pi로 그대로 옮길 수 있는 코드"를 목표로 한다.

## 1. 프로젝트 한 줄 요약

oneM2M Hackathon 2026 출품작 "중장비 근접 위험 감지 및 자동 정지 시스템".
지게차 후방의 작업자를 **태그 없이** 레이더(LD2450)와 카메라로 찾고, 충돌까지 남은 시간(TTC)을 계산해
지게차를 자동으로 감속·정지시킨다. 데이터는 oneM2M(tinyIoT)으로 주고받는다.

- 제출 마감: **2026-11-20** (최종 발표 11/23–25). 남은 기간이 짧으니 우선순위를 지킨다(14장).
- 팀: 현태(하드웨어·레이더), 광민(tinyIoT 플랫폼), 태양(MEC Sandbox), 상희(영상·AI)

## 2. 팀 저장소와의 관계

- 팀 저장소: `https://github.com/extra-7ex/Sejong_4IoT_OneM2M` (현태가 레이더까지 구현, 현재 tinyIoT로 옮기는 중)
- 이 저장소는 **참고용으로 옆 폴더에 클론**한다: `../Sejong_4IoT_OneM2M`. 비공개일 수 있으니 클론이 안 되면 사용자에게 접근 권한을 확인하라고 말한다.
- 팀 저장소에서 **확인해서 이 문서에 반영할 것**: 레이더 데이터 형식(단위·좌표·부호), tinyIoT 리소스 이름과 경로, MQTT 토픽, 사용 중인 Python 버전과 패키지, 설정 파일 위치.
  이 문서와 다르면 **팀 저장소가 기준**이다. 다른 점을 사용자에게 먼저 보고하고 이 문서를 고친다.
- 다른 팀원 코드는 **수정하지 않는다.** VisionAI는 별도 폴더(나중에 팀 저장소의 `vision/` 같은 하위 폴더나 브랜치)로 합친다.

**팀 저장소 확인 결과 (2026-10-31, 커밋 `78260b9`):** 실제 코드는 `radar/ld2450.py`, `radar/proximity.py`, `esp8266/led_server/led_server.ino`뿐이다.
docs·onem2m 스크립트·camera·engine은 빈 파일이고, README에 적힌 `radar_node.py`, `sub_alert_node.sh`, `esp8266/alert_node/`는 없다.
그래서 oneM2M 관련 내용은 대부분 **루트 README의 설계**가 근거다. Python 버전은 "Python 3"으로만 적혀 있고 requirements·설정 파일은 없다(값이 코드에 하드코딩).

**팀 저장소와 다른 점에 대한 결정 (2026-10-31, 상희):**
1. 카메라 AE: **우리 기준** — `AE-VisionAI/fusedTracks`를 쓴다. 팀 설계의 `AE-camera01/detect`는 VisionAI가 대신한다(11장).
2. 카메라 위치: 팀 그림의 "카메라 노드"가 곧 VisionAI다. 팀 그림에 맞춘 배치는 12장 "팀 구성도와의 대응".
3. 좌표 부호: 우리 좌표계(5장)를 기준으로 하고, LD2450 → 우리 좌표 변환은 config `radar.flip_x`·`flip_v`로 둔다. 실측 한 번으로 확정한다(9장).

**팀 저장소 업데이트 (2026-11-02, 커밋 `edbeae6`) — tinyIoT 연동 추가:**
- `onem2m/start_tinyiot.sh`: Pi에서 tinyIoT 서버 실행(`~/tinyIoT/source/server`, IP가 바뀌면 `config.h`의 SERVER_IP를 고쳐 재빌드).
  → **CSE = `http://<Pi IP>:3000/TinyIoT`** (HTTP, 포트 3000).
- `onem2m/setup_onem2m.sh`: AE·CNT 생성(11장 트리). `AE-camera01/detect`는 만들지만 `AE-VisionAI`는 만들지 않는다.
- `onem2m/sub_alert_node.sh`: `AE-forklift01/alert`에 구독 `sub-alert-node`(nct 1, net 3) → ESP8266 `/notify`.
  (참고: 인자로 ESP IP를 받지만 구독 주소 `nu`는 스크립트 안에 고정되어 있다 — 팀에 알릴 것, 우리가 고치지 않는다.)
- `esp8266/led_server/alert_node.ino`: 알림의 `con.level`이 `danger` 또는 `warn`이면 LED 켬. con은 JSON 객체·문자열 둘 다 받는다.
- `radar/radar_node.py`: 이름과 달리 **tinyIoT에 올리지 않는다.** `/dev/serial0`을 읽어 500mm 안이면 ESP에 HTTP `/on`·`/off`를 직접 보낸다(`proximity.py`와 거의 같음).
  → `AE-forklift01/radar`는 컨테이너만 있고 **데이터가 아직 없다.** `alert`에 쓰는 주체도 없다(엔진은 아래 브랜치, `events`에 씀).

**엔진 브랜치 `feature/riskengine-mvp` (2026-11-04, 태양, 커밋 `326deb4`, main에 아직 안 합쳐짐):** `engine/` 표준 라이브러리만 쓰는 Python AE.
- 입력: `AE-forklift01/radar/la`를 0.1초마다 GET(polling, 기본) 또는 SUB 알림(`--transport notification`, :8081/notify). CSE 기본값 `http://127.0.0.1:3000/TinyIoT`, originator `Criskengine`. 설정은 환경 변수.
- radar con: `targets[].x,y` mm, `v` cm/s(기록만), `ts`는 메타데이터. con은 객체·JSON 문자열 둘 다 받는다. CIN `ri`로 중복 제거(없으면 입력 오류).
- 판정: `SAFE`/`WARNING`/`DANGER`/`UNKNOWN`(con의 `level` = `safe`/`warn`/`danger`/`unknown`). 거리 3.0/1.5m, CPA(최근접 시각) 3.0/1.5s·반경 1.0m.
  새 CIN이 1초 넘게 없으면 `UNKNOWN` → **레이더는 사람이 없을 때도 `targets: []`를 주기적으로 올려야 한다**(엔진 README P0).
- 출력: 상태가 바뀔 때만 `AE-riskengine/events`에 CIN(con = JSON 문자열, `level` 포함). **`alert`에는 쓰지 않고 장치 제어도 없다.** fusedTracks도 아직 읽지 않는다.

**깃허브 기준 빈 연결 (2026-11-05 확인, 팀원 로컬에 안 올린 코드도 없음):**
1. 레이더 → tinyIoT: `AE-forklift01/radar`에 올리는 프로그램이 없다 → 엔진은 계속 `UNKNOWN`.
2. 엔진 → ESP: 엔진은 `events`에만 쓰고 ESP는 `alert`를 구독 → LED와 이어지지 않는다.
   **팀 설계(2026-11-05, 상희):** 엔진은 `events`와 `AE-forklift01/alert` **둘 다** 쓴다. `events`는 IN-CSE로 가는 announce(기록·관제용), `alert`는 현장 장치(ESP) 구독용.
   → 엔진 브랜치에 `alert` 쓰기가 아직 없다 → 태양에게 알린다(우리가 고치지 않는다).
3. ESP 새 펌웨어(`alert_node.ino`)는 `/notify`만 받는다 → `radar_node.py`의 `/on`·`/off`는 예전 펌웨어에서만 동작.
4. 엔진이 VisionAI `fusedTracks` 조언을 읽지 않는다 → 태양과 형식을 맞춘다.
5. **접근 권한(ACP)이 없다(2026-11-05 Pi에서 확인):** tinyIoT 기본 규칙은 "주인 AE만 접근" → 엔진(`Criskengine`)이
   `AE-forklift01/radar/la`를 읽으면 `403 originator has no privilege`. 시험은 우리 `tools/setup_test_acp.sh`로
   radar에 엔진·VisionAI 읽기(acop 34), alert에 엔진 쓰기(acop 3)를 준다. 팀 설정에도 같은 ACP가 필요 → 광민·태양에게 알림.
→ **우리가 장비 없이 먼저 채우고 팀에 알린다**(14장). 팀 코드는 고치지 않는다.

**Pi 실제 상태 (2026-11-05 SSH로 확인, 읽기만):** 깃허브 스크립트와 다르게 설정돼 있다.
- `~/tinyIoT/source/server/config.h`(11/3 변경): **MN-CSE `TinyIoT-mn`**(ri `id-mn`), 상위 IN-CSE `TinyIoT`(ri `id-in`)는 다른 컴퓨터,
  SQLite, MQTT 켬(Pi에 mosquitto 실행 중). systemd `tinyiot-mn.service`(enabled, 지금은 꺼져 있음).
  → 상희: "IN은 팀 노트북에서 돌린다"고 들음. 그런데 깃허브 스크립트·엔진은 `/TinyIoT`를 Pi 주소로 부른다 → **대회 구성은 광민에게 확인.**
- `~/Sejong_4IoT_OneM2M`은 git 없는 복사본(`onem2m/`, `radar/`만). `~/demo.sh`는 `/TinyIoT` 조회·`alert` 쓰기 시연.
- **집 시험용:** `tools/start_local_cse.sh`가 팀 `~/tinyIoT`를 `~/tinyIoT-local`로 복사해 원본 기본값(IN-CSE `TinyIoT`, SQLite)으로 돌린다.
  팀 원본은 그대로. 팀 `setup_onem2m.sh`를 그대로 돌려 AE·CNT를 만든다. Pi 안 요청은 약 1.5ms.
  나중에 MN 구성으로 가면 우리 쪽은 `onem2m.cse_name`(`TinyIoT-mn`)과 주소만 바꾼다.
- **SD카드가 아주 느리다(2026-11-05 측정):** 동기화 쓰기(fsync) 한 번에 약 340ms(카드 `SL64G`) → tinyIoT+SQLite는 CIN 하나에 **약 1.35초**.
  레이더 10Hz는커녕 1Hz도 안 돼 엔진이 `UNKNOWN`에 빠진다. **팀 원본(MN, 같은 SD카드·SQLite)도 같다 → 팀에 알릴 것.**
  우리 시험용은 DB를 RAM(`/dev/shm`)에 둬서 CIN 하나 약 2ms(재부팅하면 리소스가 사라져 `setup_onem2m.sh`를 다시 돌린다).
  대회 전 선택지: 빠른 SD카드(A1/A2 등급)로 교체, 또는 DB를 RAM에 두기 — 팀과 정한다. tinyIoT 코드는 고치지 않는다.

**아직 남은 것:**
- MQTT 토픽 — 아직 없음(HTTP만). 나오면 광민에게 받는다.
- 레이더 최종 경로(레이더 노드 vs VisionAI 업로더, 9장) — 장비가 오면 현태와 정한다.

(결정 4. fusedTracks `ts`는 팀과 같은 **Unix 초**로 한다 — 5장.)

## 3. VisionAI가 하는 일 (범위)

1. 카메라 영상에서 사람과 관절을 찾는다 — 모델 **YOLO11n-pose** 하나로 검출+자세를 함께 한다.
2. 관절로 자세를 판정한다: `standing` / `crouching` / `lying`.
3. 화면 좌표를 **바닥 좌표(m)** 로 바꾼다 — 호모그래피 보정.
4. 레이더 표적과 맞춰 보고(융합) 표적마다 상태와 **조언(advice)** 을 만든다.
5. 결과를 `fusedTracks` JSON으로 내보낸다 (처음엔 화면/파일, 나중엔 tinyIoT).

**하지 않는 일:** 감속·정지 명령을 직접 보내지 않는다. 판단과 명령은 위험 판단 엔진(다른 앱)의 몫이다.

## 4. 안전 원칙 — 반드시 지킬 것

- **AI는 조언만 한다.** `raise`는 자유. 낮추는 조언은 `lower_to_caution` 하나뿐이고 "유령 의심(ghost_suspect)" 표적에만 쓴다.
  엔진은 그 표적이 1m 밖일 때만 적용한다.
- **1m 로컬 인터락**은 차량 노드가 처리하며 VisionAI와 무관하다.
- 카메라 고장·프레임 끊김을 숨기지 않는다: `cam_ok=false`를 정직하게 보낸다. 엔진은 fusedTracks가 1초 넘게 없거나
  `cam_ok=false`면 조언을 무시하고 레이더 단독으로 판단한다.
- 애매하면 `advice: "none"`. 근거 없이 `lower_to_caution`을 내지 않는다.
- 움직임 감지(배경 차분)로 YOLO 실행을 **건너뛰지 않는다** — 가만히 쭈그린 사람은 움직임이 없어서 놓친다(12장 참고).

## 5. 좌표계와 단위

- 원점: 지게차 후면 중앙(레이더 위치) 바닥. `x`: 좌우(m), 오른쪽 +. `y`: 지게차에서 멀어지는 거리(m).
  `dist_m = sqrt(x² + y²)`. 속도 `v`: m/s, 다가오면 음수. 지연: ms.
- 시간 `ts`: **Unix 시간(초, 소수점 3자리, 예 `1761888192.340`)** — 팀 con과 같은 형식. **프레임을 찍은 시각**이다
  (CSE 저장 시각은 CIN의 `ct`, 그 차이는 `latency_ms`). 사람이 읽는 시각(+09:00)은 로그·디버그 화면에서만 바꿔 보여 준다.
- Pi에는 RTC가 없으므로 **NTP 동기화 필수**. 어긋나면 레이더–카메라 짝짓기와 엔진의 1초 판정(4장)이 틀어진다.
- 레이더 원본 단위는 LD2450 형식(9장)을 따른다 → 읽자마자 m, m/s로 변환한다.
- **팀 데이터 형식(README 4.3):** 팀의 con은 모두 `ts` = Unix 시간(초, 소수점), 거리 mm, 속도 cm/s다.
  `AE-forklift01/radar`도 원본 단위 그대로 올라오므로 받으면 m, m/s로 변환한다(`ts`는 그대로).
- **좌표계는 이 장이 기준이다.** 팀 코드에는 x 좌우 부호와 v 부호의 정의가 없다.
  레이더 값은 변환할 때 이 장에 맞춘다(9장 `flip_x`·`flip_v`). 기본값은 "LD2450 값 그대로"(x 오른쪽 +, 다가오면 v 음수로 가정).

## 6. 판단 기준 (엔진과 같은 값, config로 관리)

| 단계 | 조건 |
| --- | --- |
| 주의 (caution) | `dist < 3.0m` 또는 `TTC < 3.0s` |
| 위험 (danger) | `dist < 1.5m` 또는 `TTC < 1.5s` |
| 로컬 인터락 | `dist < 1.0m` (차량 노드) |

`TTC = dist / closing_speed` (closing_speed ≤ 0이면 TTC 없음 = null).

- 팀 README(3.2–3.3)와 임계값은 같다. 단, 팀의 상태 이름은 `safe` / `warn` / `danger`다 → 이 문서의 `caution` = 팀의 `warn`.
  팀 엔진으로 보내는 값(예: `alert`의 `level`)은 팀 이름을 쓴다.
- 팀 규칙 추가: **안전 상태가 3초 유지되면 재가동**(엔진·동작부 몫, VisionAI와 무관).
- 엔진은 `feature/riskengine-mvp` 브랜치에 있다(2장). 임계값·level 이름이 이 장과 같다. `radar/proximity.py`·`radar_node.py`는 500mm 경고 + 1.5초 해제 지연인 초기 버전이다.

## 7. 융합 규칙

- **matching 반경 0.5m**: 레이더 표적과 카메라 사람이 0.5m 안이면 1:1 짝 → `confirmed`. (헝가리안 또는 가까운 순 탐욕)
- **camera_only**: 카메라 사람인데 0.5m 안에 레이더 표적 없음.
- **ghost_suspect**: 레이더 표적인데 1.5m 안에 카메라 사람이 전혀 없고, 그 위치가 **카메라 화각 안**이며 `cam_ok=true`일 때만.
- 0.5–1.5m 사이: 짝도 유령도 아님 → `tracks`에서 제외(엔진이 레이더로 직접 판단).
- advice: `raise` = 주의 구역(dist < 3.0m) 안이고 자세가 crouching/lying 이거나 상태가 camera_only.
  `lower_to_caution` = ghost_suspect. 그 외 `none`.
- **구현(2026-11-06, `fusion.py`):** 가까운 쌍부터 탐욕 1:1. confirmed·ghost의 위치·TTC는 레이더 값, camera_only는 카메라 값(TTC null).
  "카메라 화각 안"은 보정 H로 그 바닥점이 화면 안에 찍히는지로 판정(`Calib.in_view`, 화면 아래보다 가까운 곳·카메라 뒤는 False). 보정이 없으면 유령 판정 안 함.
  ghost id = 100 + 레이더 슬롯. 출력에 `radar_id`(짝지은 레이더 슬롯), `radar_ok`(레이더 1초 안에 새 값) 필드를 더한다.
  레이더 입력 `onem2m`: `radar/la`를 CVisionAI로 10Hz 조회, 시작 때 있던 la는 버림, 1초 넘게 새 CIN 없으면 radar_ok=false.
  Pi 확인(11/6): 카메라+tinyIoT 레이더(업로더 sim) → 사람 없는 자리의 표적은 ghost_suspect, fusedTracks 70/70 올라감.
  **결정(11/6, 상희):** 유령 판정은 주의 거리(`caution_dist_m` 3.0m) 안에서만. 밖에서 엔진 경고는 TTC(빠른 접근) 때문이고 카메라가 놓칠 수 있어 낮추지 않는다.

## 8. 자세 판정과 보정

- COCO 17 키포인트(어깨 5·6, 엉덩이 11·12, 무릎 13·14, 발목 15·16), 신뢰도 낮은 점 제외.
  - `lying`: 몸통(어깨 중점→엉덩이 중점)이 수직에서 60° 이상 또는 박스 가로/세로 > 1.2
    (단, 박스가 화면 가장자리에 `edge_margin_px` 안으로 닿아 잘렸으면 박스 비율은 쓰지 않는다 — 상반신만 보여도 박스가 넓어져 오탐이 남. 2026-10-31 실측 후 변경)
  - `crouching`: (엉덩이–발목 세로 거리)/(어깨–엉덩이 길이) < 0.9 또는 무릎 각도 < 110°
  - 그 외 `standing`, 판단 불가 `null`. 최근 5프레임 다수결. 임계값은 config.
- 보정: 바닥 4점 이상 ↔ 실제 좌표(m) → 호모그래피 H → `calib/H.json`(H, 날짜, 재투영 오차).
  사람 바닥점 = **좌우는 두 발목 중점, 앞뒤는 박스 맨 아래(발끝)** (발목이 안 보이면 박스 아래 중앙, 박스가 화면 아래에서 잘리면 `box_cut` 표시).
  (2026-11-06 상희 승인으로 변경: 발목은 바닥에서 떠 있어 C270 실측에서 1.5m 점이 1.81m로 멀게 = 위험한 쪽. 박스 아래로 바꾸니 1.42m로 가깝게 = 안전한 쪽.)
  **C270 보정(11/6, 집 임시 설치 약 1m 높이·아래로 숙임):** 테이프 X 6점(±0.5m × 1.0/1.5/2.0m)을 사진에서 자동으로 찾아 계산, 재투영 오차 평균 0.5cm·최대 1.1cm.
  Pi `calib/H.json`, 노트북 `calib/H_c270.json`·`points_c270.csv`. 카메라를 숙여 2m 넘는 사람은 상반신이 잘려 자세가 None → 거리는 정상.
  카메라 설치 확인은 `tools/live_view.py`(브라우저 http://4Iot.local:8080, 안내선). **전원:** 휴대폰 충전기로 throttled=0x50000(전압 부족) → 5V 3A 필요. 노트북 웹캠은 기능 확인용이고, 최종 보정은 Pi 카메라를 실제 높이·각도로 단 뒤 다시 한다.

## 9. 레이더 입력 — LD2450

팀 확인 사항: LD2450은 UART **256000bps, 8N1**. Pi `/dev/serial0`로 읽는 것은 **프로토타입 배선**이다.
**최종 구성은 LD2450 → ESP8266 #1(D7, `Serial.swap()`)** 이고, 레이더 노드가 tinyIoT `AE-forklift01/radar`에 올린다(README 6.3).
→ 실제 시스템에서 VisionAI의 주 입력은 `onem2m`이고, `serial`은 개발·replay 녹화용이다.

**지금 상태(2026-11-02 팀 커밋):** 팀의 `radar/radar_node.py`가 Pi `/dev/serial0`을 열어 ESP에 직접 on/off만 보내고, tinyIoT `radar`에는 아무것도 올리지 않는다.
**시리얼 포트는 한 프로그램만 열 수 있다** → `radar_node.py`가 도는 동안 VisionAI의 `serial` 입력은 쓸 수 없다. 현태와 둘 중 하나로 정한다:
- (가) 팀 레이더 노드가 `AE-forklift01/radar`에 올리고 VisionAI는 `onem2m`으로 읽는다(팀 README 설계와 같음).
- (나) VisionAI가 `serial`로 읽고, 받은 프레임을 `AE-forklift01/radar`에 팀 형식으로 대신 올린다.

- 프레임 30바이트: 머리 `AA FF 03 00`, 표적 3개 × 8바이트, 꼬리 `55 CC`(28–29번째 바이트). 꼬리가 다르면 버린다.
- 표적 8바이트: X(2B), Y(2B), 속도(2B), 거리 해상도(2B, 사용 안 함), 리틀 엔디언.
  부호는 최상위 비트(1이면 양수, 0이면 음수, 나머지 15비트가 크기). 단위: X·Y mm, 속도 cm/s. 8바이트가 전부 0이면 표적 없음.
  **팀 코드 `radar/ld2450.py`의 `val()`과 같음을 확인했다.**
- 우리 좌표로 바꾸기: `x_m = ±X/1000`, `y_m = Y/1000`, `v_mps = ±V/100`. 부호는 config `radar.flip_x`, `radar.flip_v`(기본 false).
  변환은 파서 바로 다음 한 곳에서만 한다(sim·replay·serial·onem2m 공통).
  **실측으로 확정:** 레이더 앞 2m에서 오른쪽으로 걸으면 x가 커져야 하고, 레이더 쪽으로 걸어오면 v < 0 이어야 한다. 아니면 해당 flip을 true로.
- 표적 id: 팀의 radar con(`{"ts", "targets": [{"x", "y", "v"}]}`)에는 id가 없다 → 우선 **슬롯 순서(0–2)를 id로** 쓴다(잠정).
- 레이더 입력은 모두 같은 인터페이스 `get_targets(ts) -> list[Target(id, x, y, v)]`(m, m/s)로 만든다:
  1. `sim` — 시뮬레이터(13장)
  2. `replay` — 팀원이 녹화해 준 **원본 시리얼 바이트/JSON 로그**를 시간에 맞춰 재생 (노트북에서 실제 레이더 데이터로 융합 시험)
  3. `serial` — Pi에서 `/dev/serial0` 직접 읽기 (pyserial)
  4. `onem2m` — tinyIoT `radar` 구독/조회
- 같은 프레임 파서를 replay와 serial이 함께 쓴다. 파서는 pytest로 위 예시 프레임과 가짜 프레임을 시험한다.

## 10. 출력 형식 — fusedTracks (사진 한 장 = 한 건)

```json
{
  "ts": 1760936592.340,
  "frame": 1842,
  "cam_ok": true,
  "latency_ms": 142,
  "tracks": [
    {"id": 3, "state": "confirmed",     "x": 0.42, "y": 2.35, "dist_m": 2.39, "ttc_s": 1.9,  "posture": "standing",  "conf": 0.88, "advice": "none"},
    {"id": 5, "state": "camera_only",   "x": -0.9, "y": 2.6,  "dist_m": 2.75, "ttc_s": null, "posture": "crouching", "conf": 0.71, "advice": "raise"},
    {"id": 7, "state": "ghost_suspect", "x": 1.6,  "y": 3.1,  "dist_m": 3.49, "ttc_s": 4.2,  "posture": null,        "conf": 0.0,  "advice": "lower_to_caution"}
  ]
}
```

## 11. oneM2M 연동 (나중 단계)

팀 리소스 트리(README 4.1) — CSEBase 이름 **`TinyIoT`**(깃허브 스크립트 기준. Pi 실제 설정은 MN `TinyIoT-mn` → 2장), 컨테이너는 **전부 CNT(ty=3)** 이고 데이터는 CIN(ty=4)로 쌓인다.
```
TinyIoT                                [CSEBase]
├─ AE-forklift01   (Cforklift01)       radar [CNT, mni 100] ← VisionAI는 읽기·구독만
│                                      alert [CNT, mni 20] + sub-alert-node
├─ AE-zonealarm01  (Czonealarm01)      alert [CNT]
├─ AE-riskengine   (Criskengine)       events [CNT] → IN-CSE로 announce (현장 장치는 forklift01/alert를 구독)
└─ AE-VisionAI      (CVisionAI)         fusedTracks [CNT, mni 100] 위 JSON을 con에 담아 생성 → 위험 판단 엔진이 구독
                                       (camera·calib flexContainer는 14장 3순위, 팀 관례는 CNT)
```
- **결정: VisionAI는 `AE-VisionAI`를 쓴다.** 팀 README의 `AE-camera01/detect`(움직임 bbox)는 VisionAI가 대신하므로 만들지 않는다.
  팀 README 갱신은 팀원 코드·문서를 직접 고치지 말고 팀에 제안한다. originator는 팀 관례대로 `C` + 이름 = `CVisionAI`.
- radar con: `{"ts": 1760360000.12, "targets": [{"x": 373, "y": 366, "v": -8}]}` (Unix 초, mm, cm/s).
  alert con(엔진 작성): `{"level": "danger", "dist": 1200, "ttc": 1.2}` (dist mm).
- 바인딩: 지금은 HTTP, 나중에 MQTT(Mosquitto). CSE ↔ CSE(IN-CSE)도 HTTP. 엔진의 radar 구독은 아직 "예정".
- **CSE 주소(팀 `onem2m/` 스크립트, 2026-11-02):** `http://<Pi IP>:3000/TinyIoT`. VisionAI도 같은 Pi에서 돈다.
  Pi IP는 git에 넣지 않는다 → `config.local.yaml`의 `onem2m.base_url`(예: `http://<Pi IP>:3000`). 비어 있으면 오프라인 모드.
- **CIN의 `con`은 JSON 문자열로 보낸다.** tinyIoT는 객체 con을 `400 invalid attribute : con`으로 거부한다(2026-11-05 확인). 엔진·ESP는 문자열을 풀어 읽는다.
- **요청 형식(팀 스크립트와 같게):** 헤더 `X-M2M-Origin: CVisionAI`, `X-M2M-RI: <요청마다 다른 값>`, `X-M2M-RVI: 3`,
  `Content-Type: application/json;ty=<2|3|4>`, `Accept: application/json`.
- **`AE-VisionAI`는 팀 `setup_onem2m.sh`가 만들지 않는다** → VisionAI가 시작할 때 AE(`{"m2m:ae":{"rn":"AE-VisionAI","api":"NVisionAI","rr":true,"srv":["3"]}}`)와
  `fusedTracks` CNT(mni 100)를 직접 만든다. 이미 있으면(409) 그대로 쓴다. 팀 스크립트는 고치지 않는다.
- **알림 흐름(팀):** 엔진이 `AE-forklift01/alert`에 CIN → 구독 `sub-alert-node` → ESP8266 `/notify` → `level`이 `warn`·`danger`면 LED.
- 기본은 오프라인 모드(파일/화면). MQTT 토픽은 아직 없다 → 나오면 **광민의 설정**에서 가져온다. 추측해서 하드코딩하지 않는다.

## 12. 실행 환경

**목표 장비(Pi, 팀 확인 사항):** Raspberry Pi 4 Model B, **Raspberry Pi OS Lite 64-bit (Debian 13 "Trixie", 2026-09 릴리스)**,
커널 6.18, `aarch64`, 호스트 이름 `4Iot`. 데스크톱 없이(SSH) 쓰는 것으로 보인다 → **화면 없이 동작**해야 한다.
- Trixie의 기본 Python은 3.13이다. ultralytics·torch·NCNN·picamera2가 3.13에서 설치되는지는 Pi에서 **가장 먼저 확인**한다.
- Pi 카메라는 Picamera2(libcamera)로 읽는다. `python3 -m venv --system-site-packages`로 apt의 picamera2를 쓴다.
- **카메라(2026-11-05 결정):** 대회는 데모만 하면 되므로 레이더 화각 전체를 덮을 필요가 없다 → Camera Module 3 대신 **값싼 카메라**를 쓴다.
  **구매: 로지텍 C270 USB 웹캠**(2026-11-06 도착, `webcam:0`). 720p, 고정 초점, 대각 화각 55°(좁음 — 데모엔 충분), 케이블 1.5m.
  어두우면 자동 노출로 FPS가 떨어지니 데모 장소는 밝게. Pi 전원은 정격 5V 3A. `fusion.camera_fov_deg`는 도착 후 실측해 고친다.
  (피한 것: IR/NoIR — 낮에 색이 분홍빛, 130°·160° 어안 — 보정이 가장자리에서 틀어짐, 오토포커스 — 초점이 바뀌면 보정이 흔들림.)
- 모델은 NCNN 형식, 입력 320 권장. Pi 사진상 방열판이 안 보이니 쿨링 확인.
- **Pi 설치·측정 결과(2026-11-05):** Python 3.13.5 venv에 torch 2.15 **CPU판**(`--index-url https://download.pytorch.org/whl/cpu`,
  안 그러면 pip가 NVIDIA 라이브러리 수백 MB를 받다 끊긴다), ultralytics 8.4, ncnn 설치 OK. 시험 44개 Pi에서 통과.
  NCNN 320 변환 45초. 같은 영상(640×480, 2명)으로 **NCNN 320: 9.1 FPS(추론 108ms)**, PyTorch 320: 3.3 FPS(297ms).
  전체 파이프라인(추적·자세 포함, `--config config.pi.yaml`)도 약 9 FPS. 35초에 50→63°C, 휴대폰 충전기로도 throttled 0x0.
  코드는 노트북 저장소 → Pi `~/vision4iot.git`(bare) → `~/vision4iot`로 git push/pull. 모델 파일(.pt)은 scp(git 제외).

**팀 구성도(팀 README 2장)와의 대응:**

| 팀 그림 | VisionAI에서 |
| --- | --- |
| 현장 "카메라 노드 (웹캠 · OpenCV)" | **VisionAI 자체.** 카메라는 지게차 모형 후면, 레이더 바로 옆에 같은 방향으로 단다(원점·좌표 공유, 5장). |
| 카메라 노드 → CSE "detect 데이터" | `AE-VisionAI/fusedTracks` (11장) |
| MEC Pi 4B (tinyIoT · 엔진 · AI 추론) | VisionAI 프로세스도 이 Pi에서 돈다. Pi 카메라는 CSI 케이블로 연결 — 모형이 고정형이라 Pi를 모형 가까이 둔다. 멀면 USB 카메라(`webcam:0`)로 바꾼다. |
| MEC "AI 추론 (궤적 예측 · 핫스팟)" | VisionAI와 별개(팀 몫). VisionAI는 현재 위치·자세·조언만 낸다. |
| 위험 판단 엔진 | fusedTracks를 구독해 조언을 반영. 명령은 엔진이 낸다(3장). |
| 팀의 "움직임 검출" | 보조 정보로만(아래 RPiMotionCam 2번). YOLO는 매 프레임 돈다(4장). |

**지금 개발 장비(노트북):** OS는 사용자에게 확인. 가능하면 **Python 3.13**(Pi와 같게), 안 되면 3.12. 가상환경 `.venv`.

**이식성 규칙:**
- 입력 소스는 설정 하나로: `webcam:0` / 동영상 파일 / `picam`.
- 모델 경로·입력 크기·임계값·반경은 전부 `config.yaml`. Pi용은 `config.pi.yaml`.
- `--headless`면 cv2.imshow 없이 동작. 대신 **브라우저 디버그 화면(MJPEG)** 을 켤 수 있게 한다(아래).
- 의존성은 최소(ultralytics, opencv, numpy, pyyaml, pyserial). 새 패키지는 이유를 말하고 추가.
- Pi에서 자동 실행은 systemd 서비스로(나중 단계).

**참고 저장소 Qengineering/RPiMotionCam 에서 가져올 것과 안 가져올 것:**
- 안 가져옴: OS 이미지·코드 그대로 사용. Debian 10 Buster 32비트, 옛 카메라 스택, C++/FFmpeg HLS 기반이라
  우리 환경(Trixie 64비트, Camera Module 3, YOLO)과 맞지 않는다. HLS는 지연도 약 10초라 안전용으로 쓸 수 없다.
- 가져옴(아이디어):
  1. **브라우저로 보는 실시간 화면** — 우리는 지연이 짧은 MJPEG(HTTP)로, 오버레이(박스·관절·상태)를 그린 화면을 `http://<Pi IP>:8080`에 띄운다. Pi 원격 디버깅용.
  2. **배경 차분 움직임 감지** — YOLO를 건너뛰는 용도가 아니라, 화면 변화가 클 때 기록을 남기거나 디버그 표시하는 **보조 정보**로만.
  3. **SD카드 보호** — 로그·녹화는 용량 제한, 필요하면 tmpfs. 
  4. 카메라 연결 확인(`rpicam-hello --list-cameras`), 자동 실행.

## 13. 레이더가 없을 때 — 시뮬레이터

**지금 받은 장비는 Pi 4 + C270뿐이다(2026-11-05). LD2450·ESP8266·부저·지게차 모형은 아직 없다.**
그래서 없는 장비 자리를 우리 저장소의 도구로 채워 Pi 한 대에서 전체 흐름을 먼저 잇는다(팀 코드는 실행만, 수정하지 않음):
- **레이더 업로더**: 레이더 입력(sim → 나중에 serial)을 팀 형식 그대로(`{"ts","targets":[{"x","y","v"}]}`, mm·cm/s)
  `AE-forklift01/radar`에 CIN으로 올린다(originator `Cforklift01`). 표적이 없어도 `targets: []`를 주기적으로 올린다(엔진 P0).
  **sim 데이터임을 숨기지 않는다** — 로그·디버그 화면에 sim 표시. 데모에서 실제 레이더처럼 보여 주지 않는다.
- **가짜 알림 수신기**: ESP8266 `/notify`와 같은 알림을 받아 `level`을 출력(LED 대신). 구독 대상은 `AE-forklift01/alert`(팀 설계, ESP와 같은 곳). 엔진이 아직 `alert`에 안 쓰므로 그동안은 `AE-riskengine/events`도 함께 구독해 확인한다.
- **업로더 완료(2026-11-05):** `python -m vision4iot.radar_uploader --base-url http://127.0.0.1:3000` (Pi). 10Hz, con에 `"src":"sim"`,
  기본 시나리오 30초 반복(5.5m→1.0m 접근·3초 정지·떠남, 4.7m에 다른 사람, 마지막 10초 빈 `targets`). `--mode ghost`, `--dry-run`.
- **가짜 알림 수신기 완료:** `python -m vision4iot.alert_receiver` — `alert`·`events`에 구독 `sub-alert-monitor`(팀 `sub-alert-node`와 별개),
  ESP 규칙대로 `warn`·`danger`면 "LED ON". 끝날 때 구독을 지운다.
- **레이더 단독 흐름 확인(2026-11-05, Pi 한 대):** `bash tools/run_radar_flow.sh` = 수신기 + 팀 엔진(`~/riskengine`, 브랜치 `326deb4`
  그대로 복사) + 업로더. 결과: SAFE→WARNING(2.96m)→DANGER(1.49m)→WARNING→SAFE→빈 프레임 SAFE, 업로더를 멈추면 1초 뒤 UNKNOWN.
  레이더 CIN → 알림 도착 20~120ms. 엔진 시험 12개 Pi에서 통과. 팀에 알릴 엔진 동작:
  - 시작하자마자 오래된 `la`(지난 실행의 마지막 값)를 새 프레임으로 읽어 잠깐 DANGER가 나온 적 있다(센서 `ts`를 안 보기 때문).
  - 위험 없이 표적이 사라지면 1초간 `UNKNOWN(target_temporarily_missing)` 후 SAFE.
- 장비가 오면 업로더는 `serial`로, 수신기는 실제 ESP 구독으로 바꾼다.

시뮬레이터 모드:
- `from_camera`: 카메라 사람 위치에 잡음(±0.15m) → 레이더 표적. 속도 < 0.1m/s인 사람은 확률적으로 빠뜨림(레이더 약점 흉내).
- `ghost`: 고정 위치(예: 금속 선반 x=1.6, y=3.1)에 가짜 표적.
- `script`: JSON 경로대로 표적 이동(카메라 없이 융합 단위 시험).

## 14. 우선순위 (11/20 마감)

**역할 나눔 (2026-11-06, 상희 결정 — 일정이 바빠 핵심만):** 상희 = 카메라 → 사람·자세·바닥 좌표 → 레이더와 융합 → `AE-VisionAI/fusedTracks` 출력까지.
넘김: 태양 = 엔진 `alert` 쓰기·시작 직후 오래된 la 무시·fusedTracks 읽어 조언 반영 / 현태 = 실제 레이더 업로더(LD2450, 10Hz, 빈 targets)·ESP 알림 노드·대회 와이파이 /
광민 = 대회 CSE 구성(IN/MN)·ACP·SD카드 또는 RAM DB·Pi 자동 실행 / 같이 = UNKNOWN 현장 표시. 팀 공유 문서 "역할 나눔 (11/6)" 섹션에 반영(형식 포함).
→ 우리는 serial 업로더·LD2450 파서를 만들지 않는다. MJPEG 화면은 데모용으로 시간이 남으면.
**C270 연결 확인(11/6):** Pi `/dev/video0`(046d:0825), YUYV·MJPG 640×480/1280×720. 실시간 파이프라인 9.0 FPS(추론 109ms), 40초 후 50°C, throttled 0x0.

완료(노트북): 웹캠 + 사람·관절·FPS → 자세 → 보정 도구.
**바뀐 순서 (2026-11-05, Pi를 먼저 받아서):**
1. Pi 연결: SSH → tinyIoT 실행 → C270으로 VisionAI 실행·FPS(NCNN 320)
2. 레이더 업로더(sim) + 가짜 알림 수신기 → 엔진(팀 브랜치)까지 이어서 레이더 단독 흐름 확인 → 빈 곳과 채운 방법을 팀에 정리해 알림
3. 융합 → fusedTracks를 `AE-VisionAI`에 출력 → 현장 보정 → 엔진이 조언을 읽는 형식을 태양과 맞춤
4. 장비가 오면: 업로더 `serial`(LD2450 파서), ESP 구독 연결
5. 다음: MJPEG 디버그 화면
6. 여유가 있으면: camera·calib flexContainer, systemd 자동 실행, 움직임 감지 보조 정보

## 15. 폴더 구조 (목표)

```
vision4iot/
├─ CLAUDE.md, config.yaml, config.pi.yaml, requirements.txt, README.md
├─ src/vision4iot/
│  ├─ source.py      # webcam/file/picam
│  ├─ detector.py    # YOLO11n-pose + 추적
│  ├─ posture.py     # 자세 + 다수결
│  ├─ calib.py       # 호모그래피
│  ├─ radar/         # base.py(인터페이스), ld2450.py(파서), sim.py, replay.py, serial_in.py, onem2m_in.py
│  ├─ fusion.py      # 짝짓기·상태·조언
│  ├─ publisher.py   # stdout / jsonl / onem2m
│  ├─ webview.py     # MJPEG 디버그 화면
│  └─ main.py
├─ tools/  calibrate.py, bench_pose.py, record_serial.py
├─ calib/  data/  out/
└─ tests/  test_posture.py, test_fusion.py, test_ld2450.py
```

## 16. 작업 방식

- 한 번에 한 단계. 끝나면 **실행 방법과 확인할 것**을 짧게 알려 준다.
- 융합·자세·레이더 파서는 pytest 시험을 함께 만든다.
- 이 문서와 다르게 해야 할 이유가 생기면 바꾸기 전에 묻는다. 안전 원칙(4장)을 바꾸는 변경은 특히 먼저 묻는다.
- 비밀번호·토큰·IP 주소를 코드나 git에 넣지 않는다(config.local.yaml 또는 환경 변수, `.gitignore`에 추가).
