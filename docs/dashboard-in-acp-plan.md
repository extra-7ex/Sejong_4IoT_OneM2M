# IN 경유 관제 권한 적용안

## 시험 범위

2026-11-21 별도 IN 시험 AE `Cdashtest…`와 MN 시험 CNT에서 IN이 요청 origin을 `/id-in/Cdashtest…`로 전달하고, 해당 식별자에 RETRIEVE(2)만 허용하면 IN 경유 CIN 조회가 성공함을 확인했다. 다른 식별자의 조회와 관제 AE의 DELETE는 403이었다. MN 시험 CNT에 기존 ACP와 관제 ACP를 함께 연결한 경우 기존 소유자 조회도 성공했다. ACP가 없던 별도 시험 CNT에서 `acpi`를 추가한 뒤 `null`로 제거해 원래 상태를 복구했다. 시험 AE들은 삭제했다.

## 운영 적용 결과 (2026-11-21)

명시적 승인 후 IN의 `AE-dashboard-in` / `Cdashboard`를 등록하고, 아래 여섯 CNT에 관제 조회 정책을 연결했다. IN 경유 MN의 다섯 최신 CIN과 IN 이력 최신 CIN을 `Cdashboard`로 조회해 HTTP 200을 확인했다. `CNoAccess`의 radar 조회는 403이었다. `Criskengine`, `CmecIPE`, `Cforklift01`, `CVisionAI`의 기존 CNT 조회는 유지됐다. 해당 확인은 기존 작성자의 새 CIN 생성이나 ESP 물리 동작까지 증명하지 않는다.

변경 전 CNT의 RI와 `acpi` 백업은 작업 노트북 `%TEMP%/safezone-dashboard-acp-backup-20261121-010733.json`에 있다. MN의 새 ACP는 `AE-riskengine` 아래 `acp-dashboard-read`, `acp-dashboard-events-owner`, `acp-dashboard-ipe-owner`이며, IN의 이력 ACP는 `AE-safezone/acp-dashboard-history`다. 원래 ACP 참조는 유지했고, 명시적 ACP가 없던 CNT에는 기존 AE 소유자의 권한을 보존하는 규칙을 추가했다. `pvs`는 `CAdmin`만 허용한다.

## 적용한 정책과 남은 검증

- 노트북 IN에 관제용 AE `AE-dashboard-in`과 AE-ID `Cdashboard`를 등록한다. 두 이름과 ID가 실제로 비어 있는지 적용 직전 재확인한다.
- IN 경유 요청이 MN에서 `/id-in/Cdashboard`로 도착하는 것을 다시 확인하고 해당 식별자에 필요한 RETRIEVE(2)만 준다. DISCOVERY, CREATE, UPDATE, DELETE는 부여하지 않는다.
- `AE-forklift01/radar`, `AE-forklift01/alert`, `AE-VisionAI/fusedTracks`는 현재 기존 `acpi`가 있다. 기존 참조는 모두 보존하고 관제 조회 ACP를 추가하는 방안을 시험한다.
- `AE-riskengine/events`, `AE-mecIPE/MecServices/safezone-vision/status`는 확인 당시 명시적 `acpi`가 없고 상위 AE의 소유자 기본 정책을 사용한다. 별도 정책을 연결한다면 각각 `Criskengine`, `CmecIPE`의 기존 소유자 권한을 보존해야 한다. 정책 연결 전후 실제 작성자의 권한을 검증한다.
- IN의 `AE-safezone/events` 이력 조회에도 별도 RETRIEVE가 필요하다. 현재 작성자 `Csafezone`의 기존 권한을 보존한다. IN 이력의 `rcn=4` 초기 조회는 운영 데이터와 빌드에서 아직 검증되지 않았다.
- ACP의 `pvs`는 실제 관리자 `CAdmin`에게만 둔다. IN CSEBase 및 MN CSEBase에는 새로운 관제 권한을 자동 부여하지 않는다. MN 연결 확인은 권한을 부여한 radar 조회 경로로 한정할 수 있다.

## 적용과 복구

적용 전 각 CNT의 RI와 `acpi`, 연결된 ACP의 `pv`·`pvs`, 작성자와 백업 위치를 다시 확인한다. 빈 `acpi`와 속성 자체가 없는 경우를 구분해 기록한다. 다른 담당자의 변경이 감지되면 덮어쓰지 않는다.

독립 환경에서 정책 조합을 다시 검증한 뒤 하나씩 연결하고, 허용 조회·다른 식별자의 거부·기존 엔진/IPE/브리지 동작을 확인한다. 실패하면 기록한 `acpi`를 되돌리고, 원래 속성이 없던 경우 제거가 가능한지 해당 버전에서 재확인한다. 새 ACP와 AE는 더 이상 참조되지 않는 것을 확인한 뒤 정리한다. 운영 CNT의 CIN을 시험용으로 생성하거나 삭제하지 않는다.

대시보드의 `DASH_CSE_BASE`는 IN 원격 경로, `DASH_ORIGIN`은 관제 AE-ID로 지정한다. `DASH_IN_BASE`는 별도 이력 경로다. 새 대시보드는 별도 포트에서 먼저 시험하고 기존 시연 서비스를 보존한다.
