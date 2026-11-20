# Pi tinyIoT 빌드 기록

2026-11-20 Pi에서 실행 중인 MN은 `/home/user/tinyIoT/source/server/server-codex-laptop74-foptnotify`였다. 서비스 설정은 `tinyiot-mn.service`와 해당 `.service.d/` drop-in으로 구성된다. 실행 파일 SHA-256은 `0c875e2881e6745bc1f097722440d9f16863a823f5b0cf3775a6e8382052acfe`다.

Pi의 `/home/user/tinyIoT` 작업 트리 기준 커밋은 `c140495`이며, 이 저장소의 tinyIoT와 별도 체크아웃이다. `pi-source-changes.patch`는 당시 그 작업 트리에 남아 있던 세 파일의 차이로, HTTP 연결 시간 제한, SIGPIPE 무시, SQLite TEXT 처리 및 환경변수 기반 PRAGMA를 포함한다. `fopt-notify.patch`는 별도로 보존한 그룹 fan-out 알림 패치다.

**현재 작업 트리와 바이너리의 빌드 출처가 일치하는지는 확인되지 않았다.** 특히 작업 트리의 `onem2m.c`에는 fopt 패치 차이가 남아 있지 않다. 두 패치를 적용하면 기존 Pi 바이너리와 같아진다고 단정하거나 운영 서버에 바로 교체하지 않는다.

Pi `config.h`에는 MN 타입, CSE 이름과 ID, SQLite, MQTT 사용 및 원격 IN 주소 등 배포별 설정이 있으며, 현재 작업 트리의 주소가 실행 바이너리의 설정과 같다는 보장은 없다. 네트워크 주소나 자격증명은 패치에 포함하지 않았다. 설치 시 실제 MN·IN 이름과 주소, 포트, 접근 권한을 확인하고 `onem2m/config.mn.example.h`를 참고해 별도로 설정한다. MN 서비스의 PRAGMA drop-in은 WAL과 synchronous=NORMAL을 지정하고, 종료 시 재시작하도록 설정돼 있다.

재현할 때는 별도 체크아웃에서 먼저:

1. tinyIoT 원본과 실제 사용한 커밋을 확인하고, 기존 `config.h`와 DB를 안전하게 보존한다.
2. 각 패치에 `git apply --check <패치 경로>`를 실행해 충돌과 중복 적용을 확인한다. 원본·버전 차이가 있으면 내용을 검토해 조정한다.
3. 배포 설정을 별도로 작성해 빌드한 뒤 독립 CSE에서 리소스 조회, 그룹 fan-out 알림, MQTT와 HTTP, 재기동 및 DB 복구를 확인한다.
4. 기존 바이너리와 서비스 설정을 보존하고 운영 전환은 별도로 계획한다.

실행 중인 SQLite의 DB 파일 하나만 복사해 백업하지 않는다. WAL을 포함한 일관된 온라인 백업 또는 합의된 중지 후 백업을 사용한다.
