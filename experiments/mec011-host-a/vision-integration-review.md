# 실제 VisionAI 연동 조사

상태: 코드 조사만 수행. 실제 VisionAI, MN-CSE, 카메라, RiskEngine 및 MEC 연동 미시험. 기준: 이 브랜치에 포함된 코드이며 최신 팀 브랜치와의 일치 여부는 별도 확인 필요.

- `vision/src/vision4iot/main.py`는 영상 및 레이더 데이터를 융합하고 publisher에 전달한다.
- `vision/src/vision4iot/publisher.py`의 `OneM2MPublisher`는 `AE-VisionAI/fusedTracks`에 CIN을 생성한다. 출력은 자체 Vision 결과 조회 API가 아니라 oneM2M CSE를 통한 데이터 발행이다. `vision/src/vision4iot/webview.py`는 TODO이다.
- `vision/src/vision4iot/fusion.py`의 `message()`는 `ts`, `frame`, `cam_ok`, `latency_ms`, `tracks`와 선택적 `radar_ok`를 만든다. 데이터 유효성·좌표계·시간 및 단위는 실제 구성과 별도 확인 필요.
- `discover_mock_vision.py`는 단순한 모의 HTTP API 응답을 기대하므로 실제 CIN을 그대로 읽을 수 없다. 이 브랜치의 `engine/main.py`는 radar 입력을 사용하며 fusedTracks 읽기는 확인되지 않는다. 다른 브랜치의 기능으로 일반화하지 않는다.

검토할 연결 방식: MEC011에 CSE의 실제 fusedTracks 조회 인터페이스 정보(주소·경로·인증 방식)를 등록하고 소비자가 discovery 후 CSE에서 oneM2M 형식으로 조회한다. 이는 Vision 프로세스 자체의 직접 API 발견이 아니라 CSE를 통한 데이터 접근 경로 발견이다. 또는 Vision 앞에 별도 API adapter를 둘 수 있으나 추가 개발 및 별도 명세가 필요하다. 서비스 명칭, 다중 zone 매핑, originator·ACP, 가용성 및 오래된 CIN 판정은 합의 필요. 조회 성공은 Vision이 살아 있음을 보장하지 않는다.

다음 검증: 격리된 CSE와 모의 CIN을 이용해 discovery → oneM2M latest 조회·con 파싱을 시험한 뒤, 실제 Vision·CSE와 별도 시험한다. 안전 경고나 위험 판정에는 아직 연결하지 않는다.

## MEC 경로 등록·발견 실측 (2026-11-15)

Windows의 격리 실험 MEP에 임시 서비스 `safezone-cse-discovery-probe-20261115`를 등록하고 삭제했다. 시험 앱 `safezone-vision-test`를 사용했고 실제 CSE 등록은 아니다.

- 가상의 로컬 `http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la` URI를 서비스 `transportInfo.endpoint.uris`에 등록: HTTP 201.
- 이름으로 검색: HTTP 200, 동일한 URI와 ACTIVE를 반환. URI는 접근 가능한 서버인지 확인하지 않고 등록한 예시이므로 Vision/CSE가 살아 있다는 증거가 아니다.
- 위 URI 조회: 연결 거부. 해당 로컬 포트에서 CSE가 응답하지 않았으며 CIN 파싱 미검증.
- 임시 서비스 삭제: HTTP 204. 기존 서비스는 유지했다.
- 현재 실행 환경에서 Docker 명령은 PATH에 없고 `wsl --status`는 E_ACCESSDENIED. 격리 CSE 기동 및 실제 CIN 생성·조회는 실행하지 못했다.

이 시험에서 127.0.0.1은 소비자가 실행되는 기기 자신을 의미한다. 다른 Host가 사용할 실제 주소가 아니며 Originator, ACP, 실제 경로, 시간 및 데이터 신선도 판정은 별도 검증해야 한다.
