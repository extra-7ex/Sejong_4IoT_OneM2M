# CSE 명명안과 RPi 전환 안내

## 적용 전 확인

이 저장소의 운영 기본값은 팀 제안 이름 `TinyIoT-MN`이다. 실제 RPi 및 IN-CSE의 설정과 데이터는 이 변경으로 바뀌지 않는다. 적용 상태와 MQTT 응답은 미검증이다. 장비 담당자와 플랫폼 담당자가 실제 구성을 확인한 후 전환한다.

| 구분 | MN (RPi) | IN (클라우드) |
|---|---|---|
| CSEBase 이름 `rn` | `TinyIoT-MN` | `TinyIoT-IN` |
| CSE ID `csi` 제안 | `/tinyiot-mn` | `/tinyiot-in` |
| CSEBase 리소스 ID `ri` | 실제 조회값 기록 | 실제 조회값 기록 |

`rn`, `csi`, `ri`는 서로 다르다. 이전 관찰 기록의 `id-mn`은 `ri`로 적혀 있으며 `csi`라는 근거는 없다. 대소문자도 정확히 맞춘다.

## Pi 담당자와 진행할 순서

1. 현재 실행 중인 tinyIoT 및 IN-CSE의 CSEBase를 조회해 `rn`, `csi`, `ri`, 주소, 버전, MQTT 설정과 각 AE·CNT·SUB·ACP 존재 여부를 기록한다. 저장소 문서의 이전 관찰은 현재 상태를 보장하지 않는다.
2. 플랫폼 담당자와 데이터베이스 보존·복원 및 롤백 방법을 확인한다. 이름이나 ID를 바꿨을 때 기존 리소스와 등록 관계가 어떻게 되는지 현재 버전에서 확인한다. 데이터 삭제나 DB 초기화를 기본 절차로 사용하지 않는다.
3. 설치된 tinyIoT 버전의 설정 방법을 확인하고 MN과 IN 설정 및 CSE 간 등록을 합의한 순서로 변경한다. 이 저장소는 서버의 설정 파일을 포함하지 않으며 이 PR은 Pi 설정을 변경하지 않는다.
4. 접근 주소와 MQTT 바인딩, 요청자 AE ID 및 ACP를 확인하고 아래 클라이언트 설정을 실제 값과 맞춘다. CSEBase 이름과 MQTT 토픽에 쓰는 CSE ID를 혼동하지 않는다.
5. CSEBase 조회, 기존 리소스와 구독 조회, MQTT 요청의 응답 `rqi/rsc`, 생성된 `radar/la` 확인, RiskEngine·Vision 입력을 순서대로 확인한다. 실제 장비와 경보의 전체 연결은 별도로 확인한다.

## 클라이언트 설정

- RiskEngine: `ONEM2M_CSE_BASE=http://<Pi 주소>:3000/TinyIoT-MN`. 현재 Pi가 기존 이름이면 그 이름을 환경 변수로 지정한다.
- `onem2m/setup_onem2m.sh`, `onem2m/sub_alert_node.sh`: `ONEM2M_CSE_BASE`로 실제 CSE 주소를 지정할 수 있다. 두 스크립트는 CSE 리소스를 수정하며, 특히 구독 스크립트는 기존 SUB를 삭제하므로 단순 조회용으로 실행하지 않는다.
- Vision: `vision/config.local.yaml`의 `onem2m.cse_name`에 실제 이름을 지정한다. 팀 기본값은 `TinyIoT-MN`이다.
- Vision의 별도 로컬 시험 CSE는 기존 이름 `TinyIoT`를 유지한다. `vision/config.test.yaml`을 사용하며, `config.local.yaml`이 있으면 그 설정이 마지막으로 적용된다.

예상 MQTT 요청 토픽은 AE ID가 `Cforklift01`, CSE ID가 `/tinyiot-mn`, JSON 바인딩일 때 `/oneM2M/req/Cforklift01/tinyiot-mn/json`이다. 실제 버전의 토픽·응답·접근 권한은 아직 검증하지 않았다.

## 불일치나 장애가 있으면

Pi와 클라이언트의 실제 값을 기록하고 플랫폼 담당자와 원인을 확인한다. 필요하면 미리 확보한 서버 설정과 DB 복원 절차에 따라 되돌리고, 클라이언트도 기존 주소로 설정한다. 임의로 리소스를 삭제하지 않는다.

## 통합 상태 추적

아래는 이 변경을 준비한 시점의 목록이다. `미검증`은 실패를 뜻하지 않는다. 확인할 때마다 담당자, 장비·버전, 날짜, 확인 근거(응답·로그·PR)를 팀에서 기록한다.

| 연결·항목 | 현재 확인 근거 | 상태 | 다음 확인 |
|---|---|---|---|
| MN CSEBase 이름 | 저장소에 `TinyIoT`, 과거 Pi 관찰에 `TinyIoT-mn` 기록 | 실제 값 미확인 | Pi에서 `rn/csi/ri` 조회 |
| MQTT CIN 생성 | ESP가 oneM2M 요청, tinyIoT가 CIN 생성하는 구조로 팀에서 논의 | 실제 장비 미검증 | CSE ID·토픽·응답 및 `radar/la` 조회 |
| Radar CIN 형식 | 레이더 좌표 mm, 속도 cm/s를 전제로 엔진과 Vision 구현 | 실제 센서 미검증 | 단위·부호·시각·빈 프레임·슬롯 유지 확인 |
| Vision → RiskEngine | Vision의 `fusedTracks`와 엔진의 레이더 입력이 별개 | 연결 미구현 | 스키마·좌표계·표적 ID 및 판단 우선순위 합의 |
| RiskEngine → 장비 | 엔진이 `events`에 쓰며 현장 `alert`에 쓰지 않음 | 연결 미구현 | alert 생성·구독·실제 장치 동작 확인 |
| CSE 간 연결 | 문서에 IN-CSE 전달 구상이 있음 | 설정·전달 미확인 | 실제 MN/IN 설정 및 데이터 전달 확인 |

새 통합 이슈를 발견하면 같은 형식으로 원인과 재현 조건을 적고, 실제로 확인하기 전까지 완료로 표시하지 않는다.
