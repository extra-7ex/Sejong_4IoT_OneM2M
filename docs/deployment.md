# SafeZone 배포 및 운영 기록

## 2026-11-20 실장비 스냅샷 (18:45 KST, 재연결 후속 보고 전)

이 절은 재연결 후 18:45 KST에 수행한 읽기 전용 점검의 스냅샷이다. 그 뒤 작업자가 추가로 수행한 장비 복구 결과는 다음 절에 기록한다. Pi의 프로세스, systemd 설정, oneM2M 리소스, ACP, RiskEngine 로그는 읽기 전용 조회로 확인했다. ESP의 물리 동작과 Vision 시험 결과는 작업자가 수행해 알려 준 내용이다.

| 구성 | 최신 확인 |
|---|---|
| 실행 중 | `tinyiot-mn`, `tinyiot-in-local`, `mosquitto`, `safezone-radar`, `safezone-engine`, `safezone-bridge`, `safezone-dashboard`, `safezone-ipe` |
| Radar → MN | LD2450 입력을 저장소의 `radar/radar_node.py`가 MQTT CIN 요청으로 기록. 현재 `RADAR_LOCAL_DECISION=0`, 따라서 alert writer는 RiskEngine으로 분리됨 |
| RiskEngine | `/opt/safezone/engine-freshness-20261119`; `--transport polling`, `--vision-path /AE-VisionAI/fusedTracks/la`, `--alert-path /grp-safezone-alarms/fopt`. radar와 Vision latest CIN을 HTTP GET으로 읽고 events·alert를 HTTP로 씀 |
| 경보 그룹 | `grp-safezone-alarms`의 `mid`에 forklift·worker·zone alert CNT의 현재 RI 세 개가 있음. worker AE 재등록 후 새 worker alert RI가 그룹에 다시 포함됨 |
| 경보 기록 | 세 alert CNT 모두 최신 `level=danger` 기록. 작업자는 worker ESP가 위험 모드로 바뀐 것을 확인했고, 두 ESP 보드 동작도 확인함 |
| SUB | Forklift SUB는 HTTP `/notify` 주소를 직접 보유. Worker SUB는 `nu=Cworker01`이며 AE-worker01의 `poa`로 해석됨. 이번 확인에서 worker 위험 모드 경로 성공 |
| ACP | radar/fusedTracks 조회와 alert 작성용 ACP 확인. Worker ACP의 `CAdmin` 권한 마스크는 35(create/retrieve/discovery)로 설정돼 있어 최소 권한 검토는 별도 필요 |
| Vision (18:45 스냅샷) | 직전 Vision 시험에서 `cam_ok=true`, `tracks=[]`의 fresh CIN과 RiskEngine fresh 판정을 작업자가 확인. 이후 이 읽기 전용 조회 시 `safezone-vision.service`는 비활성·비활성화 상태였고 최신 CIN은 약 13분 전 |
| 최신 DANGER 원인 | 18:44 KST 엔진 기록은 radar 기반 `predicted_cpa_inside_radius_within_danger_time`; 그 시점 Vision은 stale. 해당 DANGER를 카메라 인식 결과가 유발했다고 주장하지 않음 |
| IN·대시보드 | 브리지는 Pi MN의 events를 HTTP polling해 노트북 Docker IN에 쓰며, 대시보드는 MN live 상태와 IN 이력을 표시. Pi 자체 IN도 실행 중이나 현재 브리지·대시보드 대상은 노트북 IN |
| 타이밍 | `RISK_WARNING_DISTANCE_M=2.5`, `RISK_DANGER_DISTANCE_M=1.5`, `RISK_STALE_AFTER_S=5`, `RISK_MAX_SAMPLE_INTERVAL_S=5` |

## 2026-11-20 장비 복구 후속 보고 (작업자 확인)

18:45 스냅샷 뒤 두 ESP를 다시 동작시켰다. worker AE 재등록으로 바뀐 alert CNT RI를 경보 그룹에 다시 연결한 다음, DANGER가 세 alert CNT 각각에 기록되고 worker ESP가 위험 모드로 들어가는 것을 확인했다. 두 ESP 보드가 동작하는 것도 확인했지만, 이 후속 보고에서 직접 관찰한 알림 출력은 worker ESP의 위험 모드다. 이전 11월 15일·18일 모형 시험의 서보·부저 결과는 별도의 역사적 시험 결과다.

C270은 Pi에서 인식됐다. VisionAI를 systemd 서비스가 아니라 `/home/user/vision4iot` 실행 환경에서 시작해 새 `fusedTracks` CIN을 만들었고, RiskEngine이 입력을 `fresh`로 읽는 것까지 확인했다. 그 CIN의 `tracks`는 비어 있었다. 따라서 카메라 입력 및 RiskEngine 전달 경로를 확인한 것이며, 그 시험에서 사람 검출이나 지속 실행을 확인한 것은 아니다. 앞의 18:45 조회에서 기록한 Vision stale 상태는 이 수동 재실행보다 앞선 관찰이다.

RiskEngine의 production 모듈 여덟 개는 제출 브랜치와 줄바꿈을 정규화해 비교했을 때 일치했다. Pi radar 파일의 로컬 fallback 거리 상수를 제출 브랜치에 반영했다. 운영에서는 `RADAR_LOCAL_DECISION=0`이라 이 로컬 판정은 비활성이고, 알림 writer는 RiskEngine이다. VisionAI의 실행 소스 다섯 파일도 제출 브랜치와 일치했다. Pi 전용 `config.pi.yaml`과 카메라 보정 CSV는 장비별 설정·자료라 제출 브랜치에 섞지 않았다. 주소와 계정은 공개하지 않는다.

그룹 멤버십은 worker AE를 재등록하면 자동으로 따라오지 않을 수 있다. worker alert CNT의 새 RI를 확인해 group `mid`를 갱신하고, 각 alert CNT 기록과 ESP 수신을 따로 확인한다. DHCP 예약은 아직 구성하지 않았다. 2.5 m/1.5 m 임계값과 5초 설정은 팀의 시연용 값이며 안전 한계나 추적 정확도를 뜻하지 않는다. MEC 관련해서는 Pi의 IPE가 서비스 상태를 oneM2M 리소스로 드러내는 점을 확인했다. 별도 MEC 플랫폼에서 추론을 실행하거나 지연 개선을 측정한 것은 아니다.

## 이전 배포 스냅샷의 기준

아래의 첫 점검 기록은 2026-11-20 장비 재연결 전 상태를 보존한다. Pi의 애플리케이션 저장소는 `430c8c7178e9668ac742e30a5295cb6169255b8f`이고 레이더 업로더에 로컬 변경이 있다. 엔진은 저장소 checkout이 아니라 `/opt/safezone/engine-freshness-20261119`에서 실행한다. 따라서 저장소 `main` 또는 Pi의 애플리케이션 HEAD만으로 운영 코드를 재현할 수 없다.

GitHub `main`은 이 기록을 시작할 때 `f31e63c385524f01b5f51feb186eb1f34f87d8fa`였다. Pi 운영 엔진과 해당 코드의 파일별 차이를 이번 제출 브랜치의 `engine/`에 반영했다. 실행 설정과 실험용 5초 시연값은 코드 기본값과 별도다.

## 확인된 실행 구성

| 구성요소 | Pi에서 확인한 위치·방식 | 역할과 경계 |
|---|---|---|
| tinyIoT MN-CSE와 Mosquitto | Pi systemd 서비스 | 현장 radar, events, alert 및 서비스 상태 리소스 |
| 레이더 업로더 | 저장소의 `radar/radar_node.py`; LD2450은 UART 입력, oneM2M MQTT 요청·응답 | 약 0.5초 간격으로 CIN 등록. 응답을 기다리는 동안 프레임을 버리는 로컬 변경 포함 |
| RiskEngine | `/opt/safezone/engine-freshness-20261119`, `python -m engine.main --transport polling --vision-path /AE-VisionAI/fusedTracks/la --alert-path /grp-safezone-alarms/fopt` | radar 최신 CIN과 Vision 경로를 HTTP GET; `events`와 경보 그룹에 HTTP CIN 생성 요청 |
| MN→IN 브리지 | Pi에서 별도 systemd 서비스 | MN의 events 최신 CIN을 HTTP polling해 요약하고 IN의 `AE-safezone/events`에 HTTP로 기록 |
| IN-CSE | 작업 노트북의 Docker 컨테이너 | 브리지 이력 저장 및 대시보드 IN 모드. Pi 안에도 별도 IN-CSE 서비스가 있으나 현재 이 화면·브리지 대상은 노트북 IN |
| 대시보드 | Pi, HTTP 8080 | MN 현재 상태와 IN 이력을 조회. 확인 당시 `/api/state`에서 두 CSE 연결이 정상 |
| MEC 상태 확인 IPE | Pi systemd 서비스 | 최신 Vision CIN의 시각과 `cam_ok`를 읽고 `AE-mecIPE/.../status`에 상태를 씀. 확인 당시 Vision `INACTIVE` |
| Vision 서비스 (18:45 스냅샷) | `safezone-vision` 설치됨, 해당 조회 때 중지 | 뒤이은 수동 실행에서 C270 인식, fresh CIN과 엔진 fresh 판정을 확인했으나 `tracks=[]`; 연속 실행은 미검증 |
| ESP 경보기 (18:45 스냅샷) | forklift 및 worker alert CNT/SUB 구성 확인 | 이 스냅샷 때 보드가 꺼져 있었음. 이후 재연결 때 두 보드 동작, 각 alert CNT의 DANGER 기록, worker ESP 위험 모드를 확인 |

MN→IN 전달은 Pi의 별도 HTTP 브리지로 확인했다. CSE 간 직접 Mcc 동기화로 부르면 안 된다. 노트북의 DHCP 주소가 바뀌면 MN 상위 CSE 등록 바이너리, 브리지와 대시보드가 이전 주소를 볼 수 있다. 현재 DHCP 주소 예약은 구성하지 않았다.

## 운영 RiskEngine과 저장소 코드의 차이

Pi 운영본에는 radar CIN의 `con.ts`가 Unix 시각인지, 허용 시간 범위 안인지 확인하는 가드가 있다. 시각이 없거나 오래됐거나 허용 범위보다 미래인 입력은 처리하지 않고 `UNKNOWN`으로 기록한다. `con.ts`가 boolean이면 숫자로 취급하지 않는다. velocity와 표적 연결 간격은 서버 monotonic 수신 시각으로 계산한다.

`engine/`에는 비교에서 발견한 이 동작과 관련 테스트를 반영했다. 운영 경로 파일의 기록 시각 검사는 실시간 단절 감지와 동일하지 않다. 특히 Pi 설정의 입력 stale 판정과 표적 연결 허용 간격은 5초지만 radar 센서 시각 검사는 코드 기본 최대 나이 3초다. 각각 다른 검사라, 5초 설정이 3초보다 오래된 CIN을 유효하게 만들지 않는다.

## 확인된 현재 설정

| 설정 | 실제 확인값 | 해석 |
|---|---:|---|
| `RISK_DANGER_DISTANCE_M` | 1.5 m | 팀 시연 기준, 산업안전 한계가 아님 |
| `RISK_WARNING_DISTANCE_M` | 2.5 m | 팀 시연 기준, 산업안전 한계가 아님 |
| `RISK_STALE_AFTER_S` | 5 s | 새 입력이 없다고 판정하는 시연용 설정 |
| `RISK_MAX_SAMPLE_INTERVAL_S` | 5 s | 표적 연결·속도 계산의 샘플 간격 상한. 추적 정확도는 검증하지 않음 |
| RiskEngine alert writer | `AE-riskengine` 이벤트 + `/grp-safezone-alarms/fopt` 경보 그룹 설정 | 장치가 수신했거나 실제로 정지·경보했다는 확인 아님 |
| 레이더 alert writer | `RADAR_LOCAL_DECISION=0` | 경보 CIN 기록 주체를 RiskEngine으로 선택한 설정 |
| 업로더 응답 대기 | `RADAR_MQTT_WAIT_S` 기본 2 s | 기다리는 동안 새 radar 프레임을 버려 오래된 입력이 큐에 쌓이지 않게 하는 로컬 수정 |

레이더 업로더에서 MQTT 응답 약 0.26–0.28초, 간격 약 0.53초를 잠시 관찰했다. 장기 평균, 최악 지연, 거리판정 정확도는 측정하지 않았다. 최근 엔진 이벤트에는 레이더 시각 만료와 radar 입력 stale 상태가 기록됐으며 이후 새 입력의 DANGER 기록도 관찰됐다. 읽기 요청이 이어진 짧은 관찰이라 발생 원인을 특정하지 않는다.

두 개의 5초 값은 제출 시시각각의 서비스 override에서 확인한 시연 설정이다. 안전 기능의 최적값으로 읽지 않는다. 더 긴 만료는 입력 단절을 늦게 드러낼 수 있고, 더 넓은 표적 연결 간격은 좌표 기반 속도 추정의 신뢰성을 떨어뜨릴 수 있다. 실제 네트워크 지연, 센서 배치와 표적 추적을 따로 측정해 다시 정해야 한다.

## 새 환경에 설치할 때

1. Pi와 노트북을 같은 접근 가능한 네트워크에 연결한다. 노트북 Docker IN-CSE와 Pi MN-CSE가 각각 기동하고, 노트북에서 접근할 주소를 확인한다. DHCP 예약은 아직 설정되어 있지 않으므로 주소를 고정된 값으로 복사하지 않는다.
2. Pi에서 `systemd/install.sh`로 저장소 기본 서비스를 생성할 수 있다. 이 스크립트는 서비스 파일을 설치하고 daemon-reload를 하지만, 현 Pi의 모든 override, 별도 RiskEngine snapshot, 수정된 tinyIoT 바이너리까지 배포하지 않는다.
3. 별도 MN 빌드는 상위 노트북 IN의 현재 주소를 사용한다. 빌드·복사 전에 기존 파일을 백업하고 MN 바이너리에 포함된 CSE 정보와 등록 응답을 확인한다. 여기서 확인한 서버 소스 build command와 재현 가능한 빌드 레시피는 저장소에서 확인하지 못했으므로 임의로 명령을 적지 않는다.
4. 브리지의 `BRIDGE_IN_BASE`와 대시보드의 `DASH_IN_BASE`를 동일한 현재 노트북 IN 주소로 설정한다. `/etc/systemd/system/<service>.service.d/`의 기존 설정을 확인한 뒤 필요한 환경 변수를 수정하고 `systemctl daemon-reload` 후 해당 서비스를 다시 시작한다. 주소를 코드나 문서에 커밋하지 않는다.
5. 레이더 입력이 올라오는지 `AE-forklift01/radar/la`에서 확인하고 `con.ts`, `targets`, 좌표 단위를 점검한다. 엔진은 polling 기반으로 실행하며 Vision 입력을 지정할 때 해당 CNT의 최신 생성과 `cam_ok`를 별도로 확인한다.
6. 실제 `events` CIN과 응답 `HTTP 201 / RSC 2001`을 확인한다. 이어 브리지 로그와 IN의 `AE-safezone/events/la`를 확인하고, 대시보드에서 MN·IN 연결 및 같은 최신 상태가 보이는지 확인한다. 각 단계는 독립적으로 확인한다.
7. 경보 시험 전에 한 리소스의 작성 주체가 하나인지 확인한다. worker AE 재등록 뒤 현재 worker alert RI가 경보 그룹 `mid`에 연결되어 있는지 확인한다. 이번 후속 확인에서는 세 alert CNT에 DANGER가 기록되고 worker ESP가 위험 모드로 진입했다. 부저·서보·모터 정지와 재부팅 후 그룹 복구는 별도 확인 항목이다.
8. Vision을 쓸 때는 C270 인식, 새 `cam_ok=true` CIN, RiskEngine의 fresh 판정, IPE 상태를 함께 확인한다. 장비 복구 후 `/home/user/vision4iot`에서 수동 실행해 이 데이터 경로를 확인했지만 그때 `tracks`는 비어 있었다. 18:45 스냅샷에서는 Vision 프로세스가 중지되고 최신 출력이 stale이었다. 수동 실행 결과로 서비스 상시 실행이나 사람 검출 성능을 주장하지 않는다.
9. 각 시험의 시간을 기록하고, 노트북 Docker·Pi MN·엔진·브리지·화면을 다시 시작해 복구를 별도 확인한다. 해당 재부팅 후 종단 간 재검증은 완료되지 않았다.

주소나 계정 비밀은 저장소 또는 게시용 글에 넣지 않는다. 설치 스크립트의 기본값만으로 운영 Pi의 임시 설정과 전체 배치가 재현된다고 보장하지 않는다.

## 제출 시 기술 범위

확인된 범위는 Pi의 MQTT radar CIN 수집, HTTP polling RiskEngine, Vision의 fresh `fusedTracks` 입력 경로, oneM2M event·alert CIN 기록, 경보 그룹 fan-out, worker ESP의 DANGER 위험 모드 진입, MN→IN HTTP 브리지, MN·IN 대시보드 조회, MEC 상태 IPE다. 최신 작업자 보고의 Vision 시험에서 사람 `tracks`는 비어 있었다. 수동 실행으로 systemd 상시 동작을 확인하지 않았다. 11월 15일·18일 모형 시험은 SG90 포크 서보의 정지와 부저를 보고했으며, 실제 지게차 주행 모터 제어를 뜻하지 않는다. DHCP 예약, 재부팅 복구, 최악 지연, 장기 신뢰성, fail-safe 및 산업안전 검증은 주장하지 않는다.
