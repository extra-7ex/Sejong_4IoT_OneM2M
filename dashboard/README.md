# 관제 대시보드

tinyIoT CSE에 쌓이는 레이더·위험 판단·Vision 데이터를 웹 화면으로 보여 주는 프로그램이다. Python 표준 라이브러리만 쓰므로 Pi나 노트북에 따로 설치할 것이 없다.

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
| `DASH_IN_BASE` | (비움) | 연결 상태만 표시할 IN-CSE. 예: `http://127.0.0.1:3001/TinyIoT` |
| `DASH_ORIGIN` | `CAdmin` | 조회 originator. 다른 AE로 바꾸면 ACP 권한 필요(#6) |
| `DASH_RADAR_PATH` | `/AE-forklift01/radar/la` | |
| `DASH_EVENTS_PATH` | `/AE-riskengine/events/la` | |
| `DASH_FUSED_PATH` | `/AE-VisionAI/fusedTracks/la` | |
| `DASH_ALERT_PATH` | `/AE-forklift01/alert/la` | |
| `DASH_POLL_S` | `0.5` | 조회 주기(초) |
| `DASH_HISTORY` | `dashboard/data/events.jsonl` | 이력 파일 |
| `DASH_GRID_MM` | `500` | 핫스팟 격자 크기(mm) |

Pi의 CSEBase 이름이 아직 `TinyIoT-mn`이거나 AE 이름이 `forklift01`이면 `DASH_CSE_BASE`, `DASH_RADAR_PATH`를 실제 값으로 바꾼다([CSE 명명안](../docs/cse-naming.md)).

## 동작 방식과 한계

- CSE에는 **`…/la` 조회와 CSEBase 조회만** 보낸다. 과거 CIN 개별 조회나 CNT 하위 전체 조회(`rcn=4`)는 쓰지 않는다. CSE 부하를 줄이고, 다른 팀원의 CSE 상태에 영향을 주지 않기 위해서다.
- 그래서 **이력은 대시보드가 실행 중에 본 이벤트만** 남는다. 대시보드를 켜기 전의 이벤트는 기록되지 않는다. 시작 시점의 `events/la`는 화면에만 보이고 이력에는 넣지 않는다.
- RiskEngine은 상태가 바뀔 때만 `events`에 쓴다. 0.5초 안에 상태가 두 번 바뀌면 중간 것은 놓칠 수 있다. 필요하면 `DASH_POLL_S`를 줄인다.
- 이벤트 CIN에는 표적 좌표가 없다. 그래서 `WARNING`/`DANGER` 이벤트가 들어온 순간의 최신 레이더 좌표를 이력에 함께 저장하고, 그 좌표로 핫스팟을 만든다.
- `con`은 JSON 문자열과 객체 둘 다 처리한다.
- 대시보드는 읽기만 한다. CSE에 리소스를 만들거나 지우지 않는다.

## IN-CSE로 옮길 때

README의 원래 구상은 IN-CSE(클라우드)의 이력을 대시보드가 보는 것이다. 지금은 MN의 `events`가 IN으로 전달되는 경로가 없어서, 대시보드가 MN을 직접 읽는다. 전달 경로(announcement 또는 복사용 AE)가 생기면 `DASH_CSE_BASE`와 `DASH_EVENTS_PATH`만 IN 쪽 값으로 바꾸면 된다.

## 시험

```bash
python3 -m unittest dashboard.test_dashboard
```

- 확인함: 가짜 CSE로 화면·API·이력 저장·핫스팟 표시
- 미확인: 실제 Pi MN-CSE와 실제 레이더·RiskEngine 데이터
