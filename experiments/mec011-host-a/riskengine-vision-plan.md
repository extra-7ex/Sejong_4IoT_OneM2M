# RiskEngine Vision 관찰 연결 계획

상태: 설계·실험 정리. 기존 engine 코드는 수정하지 않았고 실제 RiskEngine-MEC 통합은 미구현.

## 코드 기준 (2026-11-15)

- GitHub `main`과 Draft PR #14 (`feature/riskengine-mqtt`, `57ffdcb`)에는 `engine/fused_tracks.py`가 없다. #14는 MQTT radar 수신과 events 출력이 목적이며 Vision 조회는 포함하지 않는다.
- 별도 로컬 `work/fused-polling-mvp/engine/fused_tracks.py`는 Git 저장소가 아닌 작업 사본이다. 파일 SHA-256 `B99A0E36C6556DC08BBB364C60D7B7BD39AE6BD59E32118D19F0752988AED3BA`. GitHub 브랜치·커밋과 동일성은 미확인이다.
- 로컬 `FusedPoller`는 최초 CIN을 기준으로 대기하고 새 `ri`를 발견하면 FRESH, 동일 `ri`가 일정 시간 유지되면 STALE, 조회/파싱 오류면 ERROR로 기록한다. 별도 스레드이며 radar 판단과 events를 수정하지 않는다. `cam_ok`는 기록하지만 FRESH 판정에는 반영하지 않고 producer `ts`도 검사하지 않는다.
- `test_mec_fused_observer.py`는 위 로컬 코드를 외부에서 불러 시험용 어댑터로 연결했을 뿐, 실제 엔진에 discovery가 추가된 것이 아니다.

## 제안: 별도 엔진 PR, 관찰 전용

1. 기준은 작업 시작 시점의 최신 main과 #14 상태를 확인해 정한다. #14와 동일 파일이 겹치면 개발자와 조율한다. 기존 MEC 실험 PR에는 engine 변경을 섞지 않는다.
2. 기존 레이더 판단·events 경로를 보존하고 Vision 관찰기를 독립 입력 경로로 구현한다. 최초 기존 la는 대기, 새 CIN의 ri 갱신과 마지막 갱신 monotonic 시각을 추적한다.
3. 별도 `discovery` 구성요소가 정해진 서비스명과 zone으로 MEC에 질의한다. 결과가 없거나 복수이면 불명확 상태를 기록하고 Vision 관찰을 보류한다. timeout·오류는 지수 백오프와 상한을 둬 재시도하며 레이더 처리 루프를 막지 않는다.
4. 발견된 URI를 곧바로 신뢰하지 않는다. scheme·host·port·경로의 명시적 허용 목록을 검증하고 리다이렉트를 차단한다. 시험에서는 로컬 HTTP만 사용하며 배포에서는 인증·TLS와 권한을 따로 정한다. 주소 검증 전 Originator나 인증정보를 전송하지 않는다. discovery 응답 자체의 신뢰 및 인증은 추가 과제다.
5. oneM2M GET에는 구성 가능한 Originator/RVI를 사용한다. HTTP 및 oneM2M 응답, CIN ri, 문자열 또는 객체 con을 확인한다. 403은 권한 오류, 연결 거부/시간 초과는 연결 문제, 404는 경로 또는 데이터 부재 가능성으로 별도 기록한다. 특정 원인을 응답 없이 단정하지 않는다.
6. 상태를 별도 축으로 기록한다: 서비스 발견 상태, CIN 갱신 여부(수신 monotonic), payload 유효성/`cam_ok`, producer ts 나이 및 시계 불확실. 새 CIN이어도 오래된 촬영 시각·cam_ok=false면 사용 가능하다고 표현하지 않는다. 생산자 시각 비교는 동기화·단위·측정 시점을 확인했을 때만 가능하다. ts가 미확인이라면 UNKNOWN으로 표시한다.
7. Vision 실패·오래됨·시간 불확실은 Vision 조언 미사용으로만 처리한다. 레이더가 정상일 때 기존 radar 판정을 덮어쓰지 않는다. UNKNOWN 경보·최종 융합 규칙은 팀 합의 후 별도 PR에서 다룬다.

## 시험 및 미결 사항

- 테스트: 발견 성공/0건/복수/timeout, 허용되지 않은 URI 및 redirect, 403/404/연결 실패, 첫 CIN/반복 ri/새 ri, 지연된 새 CIN, cam_ok=false, 미래 ts, 오류 후 복구. 모의 CSE와 단위 시험부터 수행한다.
- 실제 Vision CIN 원본과 버전·좌표계·ts, 시계 동기화, CSE 경로·ACP, 서비스명·zone 식별, stale 임계값, 다중 Host discovery는 미확정이다. 기본값 3초와 0.5초는 실험 가설이다.
- 공개 서비스 등록 정보는 접근 경로 발견을 뜻하며 Vision 프로세스의 생존 또는 데이터 신선도를 보장하지 않는다. 자동 장애 감지·표준 적합성도 미검증이다.
