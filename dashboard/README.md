# 관제 대시보드

tinyIoT CSE에 쌓이는 레이더·위험 판단·Vision 데이터를 웹 화면으로 보여 주는 프로그램이다. Python 표준 라이브러리만 쓰므로 Pi나 노트북에 따로 설치할 것이 없다.

**현재 녹화 시연 구성:** dashboard는 노트북에서 실행한다. Pi MN-CSE에서 현재 상태를 읽고, Pi bridge가 노트북 IN-CSE에 복사한 이벤트 이력을 표시한다. Pi의 port 8080 dashboard unit은 임시 로컬 화면이며 시연 시스템 아키텍처에는 포함하지 않는다.

화면 구성:
- **현재 상태**: RiskEngine의 최신 판정(`SAFE`/`WARNING`/`DANGER`/`UNKNOWN`), 사유, 거리, `t_cpa`, `d_cpa`
- **위험 구역 맵**: 레이더 좌표계(지게차 기준, 전방 6 m, 시야각 ±60°) 위에 레이더 표적, Vision 추적, 위험·주의 거리 원, 핫스팟
- **데이터 수신 상태**: radar, events, fusedTracks, alert 각각의 수신 여부와 마지막 갱신 시각, MN/IN-CSE 연결 상태
- **통계·기록**: 1시간/24시간/7일 동안의 상태 전환 횟수, 위험 이벤트 기록

```text
tinyIoT MN-CSE ──GET …/la (0.5초)──▶ dashboard/server.py ──/api/*──▶ 브라우저
                                          └─ data/events.jsonl (이력)
```

## 실행

저장소 루트에서:

```bash
# Pi에서 MN-CSE와 같이 실행할 때 (기본값: http://127.0.0.1:3000/TinyIoT-MN)
python3 -m dashboard.server --port 8080

# 다른 기기에서 Pi를 볼 때
DASH_CSE_BASE=http://<RPI_IP>:3000/TinyIoT-MN python3 -m dashboard.server --port 8080
```

PowerShell에서는 `$env:DASH_CSE_BASE="http://<RPI_IP>:3000/TinyIoT-MN"`을 먼저 실행한다. 브라우저에서 `http://<실행한 기기 IP>:8080`을 연다.

### 노트북 시연 구성

노트북에서 실행할 때는 Pi MN 주소와 노트북 IN 주소를 각각 지정한다. 실제 주소는 DHCP 환경에서 실행 직전에 조회한다.

```bash
DASH_CSE_BASE=http://<PI_IP>:3000/TinyIoT-MN \
DASH_IN_BASE=http://<NOTEBOOK_IP>:3000/TinyIoT \
python3 -m dashboard.server --port 8080
```

Pi에서 bridge를 실행할 때도 `BRIDGE_IN_BASE=http://<NOTEBOOK_IP>:3000/TinyIoT`로 설정한다. MN의 Mcc 등록은 별도 CSE 연결 관계이고, event history는 bridge의 HTTP/Mca create 경로로 이동한다.

### IN을 통한 MN 원격 조회 시험 (2026-11-21)

기존 대시보드는 `DASH_CSE_BASE`에 IN의 원격 CSE 경로를 넣어 현재 상태를 IN을 통해 조회할 수 있다. 다음은 시험한 주소 형식이며 Pi와 노트북 주소, CSE ID 및 접근 권한은 실제 환경에 맞춰 확인해야 한다.

```bash
DASH_CSE_BASE=http://<IN_IP>:3000/~/tinyiot-mn/TinyIoT-MN \
python3 -m dashboard.server --port 8080
```

요청은 대시보드 → IN의 Mca/HTTP, IN → MN의 Mcc로 전달된다. Pi MN에 별도 시험 AE와 조회 전용 ACP를 만들고 모의 radar, fusedTracks, alert, Vision 상태, events CIN을 생성한 뒤, 기존 대시보드의 `/api/state`가 다섯 값을 모두 IN 경유로 읽는 것을 확인했다. 권한이 없는 원격 식별자는 403/RSC 4103으로 거부됐다. 시험 리소스는 삭제했다.

**운영 전환 전 확인:** 운영 radar 등에는 시험용 원격 식별자 조회 권한이 없으므로 현재 설정을 그대로 바꾸면 403이 발생한다. IN이 `CAdmin` 요청을 `/id-in/CAdmin`으로 전달하는 것을 확인했지만, 운영에는 관제 전용 식별자와 필요한 리소스의 RETRIEVE 권한을 별도로 설계하고 허용·거부를 시험한다. CSEBase 조회가 거부될 수도 있으며, 실제 시험에서 CNT 조회는 성공해도 MN 연결 표시가 HTTP 403으로 나타났다. 운영 ACP는 이 시험에서 바꾸지 않았다.

위 예제는 `DASH_IN_BASE`를 설정하지 않으므로 이력은 대시보드 로컬 모드다. IN 이력까지 사용하려면 `DASH_IN_BASE`를 별도로 지정해야 하지만, 이 경우 IN 이력 컨테이너에 `rcn=4` 조회를 수행한다. 해당 동작은 사용 중인 IN의 빌드·데이터에서 별도로 검증한다. 이 시험은 이력 불러오기를 실행하지 않았다.

대시보드의 `age_s`는 대시보드가 처음 보거나 변경을 감지한 뒤 경과한 시간으로, CIN의 원본 센서 시각 자체를 검증하지 않는다. 같은 오래된 CIN을 처음 읽으면 최근 수신으로 보일 수 있으므로 화면의 시간만으로 센서가 최신 상태라고 판단하지 않는다. 데이터 원본의 timestamp·통신 실패 표시와 복구 처리를 검증한 뒤 실제 대시보드를 전환한다.

### 장비 없이 화면 확인

가짜 CSE가 사람이 다가왔다 멀어지는 상황을 30초 주기로 흉내 낸다.

```bash
python3 -m dashboard.fake_cse --port 3900 &
DASH_CSE_BASE=http://127.0.0.1:3900/TinyIoT-MN python3 -m dashboard.server --port 8080
```

## 설정 (환경 변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DASH_CSE_BASE` | `http://127.0.0.1:3000/TinyIoT-MN` | 데이터를 읽을 CSE |
| `DASH_IN_BASE` | (비움) | IN-CSE. 지정하면 IN 연결 상태를 표시하고 위험 이력을 IN에서 읽음(IN 모드). 예: `http://127.0.0.1:3001/TinyIoT` |
| `DASH_IN_EVENTS_PATH` | `/AE-safezone/events` | IN 모드에서 읽을 이력 컨테이너(브리지가 만듦) |
| `DASH_ORIGIN` | `CAdmin` | 조회 originator. 다른 AE로 바꾸면 ACP 권한 필요(#6) |
| `DASH_RADAR_PATH` | `/AE-forklift01/radar/la` | |
| `DASH_EVENTS_PATH` | `/AE-riskengine/events/la` | |
| `DASH_FUSED_PATH` | `/AE-VisionAI/fusedTracks/la` | |
| `DASH_ALERT_PATH` | `/AE-forklift01/alert/la` | |
| `DASH_POLL_S` | `0.5` | 조회 주기(초) |
| `DASH_HISTORY` | `dashboard/data/events.jsonl` | 이력 파일 |
| `DASH_GRID_MM` | `500` | 핫스팟 격자 크기(mm) |
| `DASH_FRESH` | `1` | 실행 시각 이후 이벤트만 표시(이전 이력은 지우지 않고 화면에서만 숨김). `0` 또는 `--all`이면 전체 이력. 화면의 [화면 초기화] 버튼(`POST /api/reset`)으로 언제든 다시 비울 수 있음 |

Pi의 CSEBase 이름이 아직 `TinyIoT-mn`이거나 AE 이름이 `forklift01`이면 `DASH_CSE_BASE`, `DASH_RADAR_PATH`를 실제 값으로 바꾼다([CSE 명명안](../docs/cse-naming.md)).

## 동작 방식과 한계

- MN에는 **`…/la` 조회와 CSEBase 조회만** 보낸다. 과거 CIN 개별 조회나 CNT 하위 전체 조회(`rcn=4`)는 쓰지 않는다. CSE 부하를 줄이고, 다른 팀원의 CSE 상태에 영향을 주지 않기 위해서다.
- 로컬 모드(`DASH_IN_BASE` 없음)에서는 **이력이 대시보드가 실행 중에 본 이벤트만** 남는다. 시작 시점의 `events/la`는 화면에만 보이고 이력에는 넣지 않는다.
- IN 모드에서는 시작할 때 IN의 이력 컨테이너를 `rcn=4`로 한 번 불러온다. 이 컨테이너에는 브리지가 만든 요약 CIN(각 255바이트 이하)만 있다.
- RiskEngine은 상태가 바뀔 때만 `events`에 쓴다. 0.5초 안에 상태가 두 번 바뀌면 중간 것은 놓칠 수 있다. 필요하면 `DASH_POLL_S`를 줄인다.
- 이벤트 CIN에는 표적 좌표가 없다. 그래서 `WARNING`/`DANGER` 이벤트가 들어온 순간의 최신 레이더 좌표를 이력에 함께 저장하고, 그 좌표로 핫스팟을 만든다.
- `con`은 JSON 문자열과 객체 둘 다 처리한다.
- 대시보드는 읽기만 한다. CSE에 리소스를 만들거나 지우지 않는다.

## IN-CSE 이력 연동 (IN 모드)

MN의 위험 이벤트를 bridge가 IN-CSE에 쌓고, 대시보드가 그 이력을 보여 주는 구성이다. 현장 판단은 MN(엣지), 이력은 IN에 둔다. MN의 Mcc 등록 관계와 event-copy bridge는 별도 흐름이다.

```text
레이더 ──▶ MN  AE-forklift01/radar ──────────────────────────▶ 대시보드 (실시간 지도)
RiskEngine ─▶ MN  AE-riskengine/events ──▶ 브리지 ──▶ IN  AE-safezone/events ──▶ 대시보드 (이력·통계)
```

1. 브리지 실행 (`onem2m/mn_to_in_bridge.py`, 저장소 루트에서)
   ```bash
   python3 -m onem2m.mn_to_in_bridge
   ```
   - 처음 실행하면 IN에 `AE-safezone/events`(mni 5000)를 만든다.
   - MN의 `events/la`를 0.5초마다 보고, 새 이벤트를 IN에 요약 CIN으로 올린다. 요약 필드: `ts`, `status`, `reason`, `distance_m`, `t_cpa_s`, `d_cpa_m`, `n`(표적 수), `xy_mm`(위험 순간 레이더 좌표), `mn_ri`(MN 원본 CIN).
   - 마지막으로 올린 MN 이벤트를 `~/.safezone_bridge_state.json`에 기억해서, 재시작해도 같은 이벤트를 두 번 올리지 않는다.
   - MN이나 IN이 잠시 꺼져도 계속 재시도하고, 다시 연결되면 이어서 올린다. 꺼져 있던 동안 MN에서 여러 번 바뀐 상태는 마지막 것만 올라간다.
   - 계속 켜 두려면 `systemd/safezone-bridge.service`를 쓴다.
2. 대시보드를 IN 모드로 실행
   ```bash
   DASH_CSE_BASE=http://<PI_IP>:3000/TinyIoT-MN DASH_IN_BASE=http://<NOTEBOOK_IP>:3000/TinyIoT python3 -m dashboard.server --port 8080
   ```
   - 시작할 때 IN 이력을 불러오므로, 대시보드를 껐다 켜도 이력이 그대로 보인다.
   - 상단에 IN-CSE 연결 상태가, 이벤트 기록 제목에 `IN-CSE /AE-safezone/events`가 표시된다.

브리지 설정 (환경 변수)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `BRIDGE_MN_BASE` | `http://127.0.0.1:3000/TinyIoT-MN` | MN-CSE |
| `BRIDGE_IN_BASE` | `http://127.0.0.1:3001/TinyIoT` | 대안 local test default; 시연에서는 노트북 IN 주소를 지정 |
| `BRIDGE_EVENTS_PATH` | `/AE-riskengine/events/la` | 옮길 MN 이벤트 |
| `BRIDGE_RADAR_PATH` | `/AE-forklift01/radar/la` | 위험 순간 좌표를 읽을 레이더 |
| `BRIDGE_IN_AE` / `BRIDGE_IN_CNT` | `AE-safezone` / `events` | IN에 만들 리소스 |
| `BRIDGE_IN_ORIGIN` | `Csafezone` | IN AE 생성·기록 originator |
| `BRIDGE_MN_ORIGIN` | `CAdmin` | MN 조회 originator |

## 시험

```bash
python3 -m unittest dashboard.test_dashboard onem2m.test_mn_to_in_bridge
```

- 확인함: 가짜 CSE로 화면·API·이력 저장·핫스팟 표시, 실제 Pi MN-CSE(`TinyIoT-MN`)와 가상 레이더(`radar/sim_rader.py`)로 실시간 표시
- 확인함 (IN 모드): 실제 tinyIoT MN·IN 두 개를 띄우고 가상 레이더·RiskEngine·브리지·대시보드를 함께 실행. 이벤트 106건이 IN에 쌓였고(요약 최대 186바이트), IN 재시작 뒤에도 이력이 남고 브리지가 자동으로 이어 올림
- 실장비 시연 확인: 노트북에서 MN 현재 상태와 Docker IN 이력 조회, Pi bridge가 이벤트 요약을 IN에 기록
- 미확인: DHCP 주소 자동 예약, 재부팅 뒤 전체 경로 복구
