# 후속 이슈: UNKNOWN 무음 정책과 상태 표현 구분

상태: 후속 검토, 이번 펌웨어에서 동작 변경 없음.

작업자 부저는 UNKNOWN에서 기존처럼 무음으로 유지한다. 새 부저·LED 경보 패턴을 추가하지 않는다는 사용자 결정을 따른다. 다만 무음이라는 출력 정책을 SAFE/정상 판정과 동일하게 표현해서는 안 된다.

현재 `worker_node.ino`는 `danger`를 mode 2, `warn`을 mode 1, 나머지 level을 mode 0으로 전달한다. 실제 UNKNOWN 수신 다음 `SAFE: 조용` 로그를 관찰했다. status의 mode 0도 명시적 SAFE와 UNKNOWN을 구분하지 못한다. 이는 이번 등록·권한·그룹 연결 수정과 별개이며 자동으로 정상이라고 해석하지 않는다.

후속 검토 범위:

- 명시적 safe, unknown, 인식하지 못한 level의 내부 상태·로그·status 표현을 구분한다.
- UNKNOWN에서는 작업자 부저의 기존 무음 정책을 유지한다.
- 표현 변경이 status 소비자와 호환되는지 확인한다. mode 숫자만 바꾸어 기존 부저 루프가 울리게 만드는 변경은 피한다.
- 지게차 UNKNOWN 정지·경보, RiskEngine 판정, 등록·ACP·그룹 연결은 별도로 유지한다.

검증 기준: UNKNOWN은 부저 무음을 유지하며 SAFE/정상으로 표시되지 않아야 한다. 명시적 SAFE와 기존 WARNING/DANGER 동작을 함께 확인한다. 구체적인 내부 상태·status 스키마는 후속 구현 전에 합의한다.
