# MEC011 Host A 격리 실험

> **상태: 실험. 실제 현장 아키텍처나 완성된 MEC Host가 아닙니다.** 기존 `docs/architecture.md`를 대체하지 않습니다.

## 먼저 확인할 사항

- 이 폴더는 **노트북 한 대에서** AdvantEDGE의 MEC011 구성요소, Redis, 경로 중계기와 **모의 Vision**을 연결하는 시험입니다. 실제 VisionAI, RiskEngine, MN-CSE, 센서·경고 장치 연결은 포함하지 않습니다.
- 테스트 앱 인스턴스는 Redis에 직접 생성해 오케스트레이터를 흉내 냅니다. 이후 MEC011 `confirm_ready`를 사용합니다. **실제 자동 배포·앱 등록이나 표준 적합성을 검증한 것은 아닙니다.**
- 시험용 서비스는 고정된 합성 JSON을 반환합니다. 서비스가 죽어도 `ACTIVE`가 자동으로 바뀌지 않았습니다. 수동 상태 변경에 따른 가용성 알림은 확인했으며 heartbeat 자동 감지는 미검증입니다.
- 18080/18081 포트는 localhost 전용입니다. 인증·TLS·영구 저장소가 없으므로 외부로 노출하거나 현장 안전 제어에 사용하지 마세요. Redis는 격리된 Docker 네트워크 안에서만 사용합니다.
- 등록 결과는 일회성입니다. 컨테이너 삭제 시 데이터가 없어질 수 있습니다. 다른 프로젝트의 컨테이너·이미지를 정리하지 마세요.

## 구성 구분

**기존 프로젝트:** `docs/architecture.md`와 main의 기존 구현을 유지합니다. 이 실험은 변경하지 않습니다.

**이번 실험:** 단일 노트북의 MEC011 등록·조회 → 모의 Vision 접속. 수동 가용성 변경 알림을 확인했습니다. 실제 서비스 연동은 미완료입니다.

**팀 검토 중인 목표:** Zone A/B의 각 Host에 MEC 기능, VisionAI, RiskEngine, MN-CSE를 배치하고 구역 간 서비스·이벤트를 연계합니다. 두 실제 Host, cross-host discovery, 장애 격리, ARM64는 구현·검증하지 않았습니다.

## 실행 준비

Docker Desktop 또는 Docker Engine + Compose, Git, Python 3가 필요합니다. 빌드 시 외부 이미지를 다운로드하므로 디스크 공간과 인터넷이 필요합니다. 실행 전 18080/18081 포트 충돌 여부를 확인하세요. Linux/Windows 간 환경은 별도 검증이 필요합니다.

이 폴더에서 다음을 실행합니다. `upstream/`은 Git에서 제외되므로 공개 소스를 직접 받아야 합니다.

```bash
git clone https://github.com/InterDigitalInc/AdvantEDGE.git upstream
git -C upstream checkout 8f6edbeaf3674b6a667ce3bc1dbef3a7fccbe2b9
docker compose -p safezone-mec-experiment up -d --build
python setup_mock_app.py
python discover_mock_vision.py
```

Windows에서 `python` 대신 `py`를 쓸 수 있습니다. Docker 실행 명령이 PATH에서 인식되어야 합니다. `setup_mock_app.py`는 시험 앱을 수동 준비하고 MEP만 재시작하며 `confirm_ready`와 서비스 등록을 수행합니다. 이미 같은 시험 서비스가 등록돼 있으면 중복 생성을 막고 종료합니다.

성공 시 `READY 204; REGISTER 201`과 `PASS: MEC011 discovery -> local mock Vision response`가 나옵니다. 모의 서비스의 좌표는 실제 측정값이 아닙니다.

중지(삭제 안 함):

```bash
docker compose -p safezone-mec-experiment stop
```

## 검증 및 남은 작업

- 로컬 `confirm_ready` 204, 등록 201, 조회 200 및 반환된 `_links.self` 200 확인.
- 모의 서비스 중지 시 클라이언트 연결 실패를 확인했지만 MEC의 `ACTIVE`는 남았습니다. 서비스 복구 후 접속을 다시 확인했습니다.
- 실제 VisionAI·RiskEngine·oneM2M, Host B, heartbeat 자동 장애 감지, 인증·TLS, 장애 격리, ARM64 및 장시간 안정성은 미검증입니다.
- 기존 AdvantEDGE 구현은 Sandbox 경로를 반환하므로 nginx가 `/safezone-a/mep-a/`를 제거해 전달합니다. API 명세 파일 디렉터리 `/api`는 이미지에 포함하지 않아 관련 메타데이터 기능은 미검증입니다.

상류 코드: [AdvantEDGE](https://github.com/InterDigitalInc/AdvantEDGE), Apache-2.0, 위 커밋으로 고정. 이 저장소에는 상류 소스 전체를 포함하지 않습니다.

## MEC011 가용성 알림 시험

별도의 시험 수신기를 추가하고 서비스 상태를 **수동으로** 바꿔 알림을 확인합니다. 먼저 위의 기본 실행·등록을 완료하세요.

```bash
docker compose -p safezone-mec-experiment -f compose.yaml -f notify-test.compose.yaml up -d
python test_availability.py
```

테스트는 임시 SUB를 생성하고 시험 서비스의 INACTIVE와 ACTIVE 상태 변경 알림을 확인한 뒤 ACTIVE로 복구하고 해당 시험 SUB를 삭제합니다. 알림 수신기는 Docker 내부 네트워크 전용입니다. 한 앱 인스턴스가 발행자·구독자 역할을 흉내 내며 실제 RiskEngine은 아닙니다. 이 테스트는 명시적 상태 업데이트를 검증하며 heartbeat 장애 자동 감지·교차 Host 알림은 검증하지 않습니다.

2026-11-15 Windows/Docker 시험: SUB 201, INACTIVE/ACTIVE PUT 200, 두 상태의 `SerAvailabilityNotification` 수신 확인. 복구 후 서비스 발견 및 모의 Vision 응답 확인. 별도로 서버 경로 구현에서 heartbeat 관련 핸들러는 확인하지 못했으며 API 모델의 존재만으로 동작을 단정하지 않습니다.

### Heartbeat 구현 조사 (2026-11-15)

고정 상류 버전 `8f6edbeaf3674b6a667ce3bc1dbef3a7fccbe2b9`에서 `go-apps/meep-app-enablement/api/service-mgmt/swagger.yaml`은 `livenessInterval`과 liveness 자료형을 정의한다. 그러나 `server/routers.go`의 서비스 관리 라우트에는 liveness 요청 경로가 없고, `server/service-mgmt`의 Go 소스에서 liveness 관련 참조는 모델 선언으로만 검색된다. 따라서 현재 확인한 구성요소에 heartbeat 수신 및 만료 처리의 실행 경로는 확인되지 않았다. 모델의 존재만으로 기능을 지원한다고 판단하지 않는다. 전체 AdvantEDGE 배포 또는 다른 버전의 지원 여부까지 결론 내릴 수 없다.

이전 시험에서는 모의 Vision을 중지해도 등록 상태가 자동 변경되지 않았다. 이는 당시 설정의 결과이며 heartbeat를 활성화한 시험은 아니다. 이번 조사 환경에서는 WSL 접근이 거부되어 heartbeat API 호출·시간 초과·알림을 추가 시험하지 못했다. 외부 health check를 만들 경우 자체 구현으로 표시해야 한다.

## 격리 tinyIoT와 MEC 발견 연동 (2026-11-15)

`test_cse_discovery.py`는 별도 tinyIoT IN-CSE(테스트용 SQLite), 모의 fusedTracks CIN 및 기존 MEC 시험을 사용한다. Pi MN-CSE, 실제 Vision, 실제 위험 판단과 무관하다. CSE 소스는 `seslabSJU/tinyIoT` commit `c140495622a6271fe16c8cf92315c2892c803003`를 사용했다. 이미지 빌드와 실행 예시(WSL, Docker):

```bash
# 소스를 별도로 받아 commit을 정확히 확인한 뒤, 이 디렉터리에서 실행
# DB·비밀정보·기존 빌드 파일이 없는 깨끗한 체크아웃을 사용한다.
# Docker 빌드 컨텍스트가 source/server 전체를 이미지에 복사한다.
# tinyIoT 소스의 source/server 경로를 TINYIOT_SERVER에 지정한다.
TINYIOT_SERVER=/path/to/tinyIoT/source/server
docker build -t safezone-tinyiot-test:local -f Dockerfile.tinyiot-test "$TINYIOT_SERVER"
docker run -d --name safezone-mec-tinyiot-test --network safezone-mec-experiment_trial -p 127.0.0.1:13000:3000 safezone-tinyiot-test:local
python3 test_cse_discovery.py
```

기본 MEC 시험 환경과 `safezone-vision-test` 앱 준비가 선행돼야 한다. 이 컨테이너에는 영구 볼륨이 없고 SQLite는 컨테이너 내부에 생성된다. 이미지 로컬 크기는 약 631 MB이며 빌드 캐시는 별도 공간을 사용한다. CAdmin은 시험 전용이다. 스크립트는 무작위 이름의 AE·CNT·모의 CIN을 생성하고 MEC 임시 등록을 삭제한다. 시험 CSE의 AE·CIN은 확인을 위해 남긴다. 127.0.0.1 주소는 같은 PC에서만 유효하다. 다른 Host 접근, 인증·권한, 운영 보안은 미검증이다. 종료: `docker stop safezone-mec-tinyiot-test` (컨테이너는 삭제하지 않음).

실측: AE/CNT/CIN POST 각각 HTTP 201 및 oneM2M rsc 2001; MEC 등록 201, 발견 200; 발견한 URI로 CIN 조회 HTTP 200 및 rsc 2000; JSON 문자열 `con` 해석 PASS; 임시 MEC 등록 삭제 204. Vision 실측 결과, RiskEngine 통합, stale 판단, 실제 MN-CSE 및 두 Host 연결은 미검증이다.
