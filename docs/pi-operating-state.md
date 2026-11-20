# Pi 실장비 구성과 시험 기록

2026-11-20 확인 기준이다. IP 주소는 DHCP로 달라질 수 있다. 이 기록은 산업용 안전 성능을 보증하지 않는다.

## 현재 흐름

```mermaid
flowchart LR
  LD[LD2450] -->|UART| RAD[Pi 레이더 수집]
  RAD -->|radar CIN| MN[oneM2M MN-CSE]
  CAM[카메라] --> VIS[VisionAI]
  MN -->|radar HTTP 조회| VIS
  VIS -->|fusedTracks CIN| MN
  MN -->|radar 및 fusedTracks HTTP 조회| ENG[RiskEngine]
  ENG -->|events 및 경보 그룹 fopt HTTP 기록| MN
  MN -->|alert SUB HTTP 알림| F[지게차 ESP: 포크와 부저]
  MN -->|alert SUB HTTP 알림| W[작업자 ESP: 부저]
  MN -->|이벤트 브리지| IN[노트북 IN-CSE]
  IN --> DASH[노트북 대시보드]
  IPE[MEC 연동 AE] -->|MEC011 발견| MEC[MEC 플랫폼 등록부]
  IPE -->|fusedTracks 조회 및 상태 기록| MN
```

엔진이 경보 판단 주체이며 레이더의 LOCAL_DECISION은 비활성이다. 엔진과 CSE 사이는 현재 HTTP polling과 HTTP 기록이다. 경보 그룹에는 지게차·작업자·구역 alert CNT 세 개가 있다. MN→IN 이벤트 브리지는 별도 애플리케이션이므로 브리지 데이터 전달 자체를 Mcc로 단정하지 않는다. 최근 ACP 변경 후 세 CNT에 danger 기록을 확인했으며, 그 변경 후 ESP 알림 수신과 기기 동작은 별도 확인이 필요하다.

## 엔진 및 ACP

- 실행 경로는 `/opt/safezone/engine-freshness-20261119`, Origin은 `Criskengine`이다. radar 및 fusedTracks를 읽고 events와 `grp-safezone-alarms/fopt`에 기록한다.
- 시연 설정은 `RISK_STALE_AFTER_S=5`, `RISK_MAX_SAMPLE_INTERVAL_S=5`, 위험 거리 1.5m, 경고 거리 2.5m다. 원래 설계 기준은 stale 1초, 표본 간격 0.75초이며 시연 설정은 지연 상황에서 UNKNOWN을 늦출 수 있다. 값은 산업안전 임계값이 아니다.
- 레이더 업로더의 별도 LOCAL_DECISION 임계값은 위험 1.5m, 경고 3m다. 현재 LOCAL_DECISION은 꺼져 있어 위 엔진 값이 적용된다. 다시 켜면 판단 주체와 경고 거리 차이를 먼저 확인한다.
- 운영 그룹의 멤버는 세 개이며 `cnm=3`이다. 그룹 `macp`와 세 alert CNT ACP는 Criskengine에 CREATE를 허용한다. 소유자 권한과 작업자 CNT의 기존 CAdmin 권한은 유지했다. 무구독 시험 그룹에서 fan-out CREATE를 검증했고, 운영 전환 후 events의 HTTP 201/RSC 2001 및 세 CNT의 danger CIN을 확인했다.
- 복구본: `/etc/default/safezone.codex-backup-20261120`, `/etc/systemd/system/safezone-engine.service.codex-backup-20261120`. 적용 전 현재 drop-in과 설정을 확인한다. radar·fusedTracks MQTT SUB는 이번 전환에서 만들지 않았다.

## MEC 및 Vision

- Pi의 IPE는 `/opt/safezone/mec-discovery/mec_ipe.py`를 사용하며 systemd drop-in `/etc/systemd/system/safezone-ipe.service.d/50-mec-discovery.conf`에서 MEC011 발견을 활성화했다. 등록부 주소는 로컬 18080, 서비스명은 수동 등록한 `safezone-vision-cin-trial`이다.
- 등록된 주소는 실제 MN-CSE의 `AE-VisionAI/fusedTracks/la`다. 11월 20일 실제 VisionAI를 실행하자 IPE가 최신 CIN을 읽고 INACTIVE에서 ACTIVE로 바뀌었다. 약 2.1 FPS로 실행 중 2초 기준을 넘겨 INACTIVE와 ACTIVE 사이가 한 차례 흔들렸다. 시험 후 Vision을 종료했고 다시 INACTIVE가 됐다.
- MEC 등록부의 ACTIVE는 실제 Vision 데이터가 최신임을 보장하지 않는다. Vision 자동 서비스 등록, 다중 서비스 선택, 원격 장비 발견과 장시간 안정성은 미검증이다. 엔진은 IPE 상태 CIN을 소비하지 않는다.
- `IPE_MEC_BASE`는 등록부 주소, `IPE_DISCOVERY_CSE_BASE`는 허용할 데이터 CSE 주소다. 후자가 없으면 `IPE_MN_BASE`를 사용한다. CSE 주소 변경 시 설정도 갱신해야 한다.

## 네트워크 복구

Pi와 ESP의 IP는 DHCP로 바뀔 수 있으므로 재시작 후 현재 주소를 확인한다. 지게차 ESP의 펌웨어 CSE 주소, MN의 alert SUB 알림 주소, 작업자 AE의 등록 주소와 SUB, 노트북 IN-CSE 및 브리지 설정을 현재 주소와 대조한다. 연결 주소를 바꾸기 전 기존 설정과 리소스를 확인하고, 실제 알림과 대시보드 반영까지 시험한다. DHCP 예약은 운영 환경의 선택 사항이다.

1. Pi에서 `hostname -I`로 현재 LAN 주소를, 노트북에서 네트워크 설정으로 현재 LAN 주소를 확인한다. ESP 두 개는 각각 시리얼 모니터(115200)의 IP를 확인한다. Tailscale 주소와 LAN 주소는 서로 다를 수 있다.
2. 지게차 ESP의 Wi-Fi 정보는 `esp8266/led_server/secrets.h`에 둔다. 지게차 알림 수신 주소는 MN의 `AE-forklift01/alert/sub-alert-node`의 `nu`에 있다. `onem2m/sub_alert_node.sh <ESP IP>`는 기존 같은 이름 SUB를 삭제 후 다시 만들므로, 기존 설정·권한과 ESP 접근을 먼저 확인하고 변경 후 `nu`를 조회한다.
3. 작업자 펌웨어의 Wi-Fi와 `CSE_HOST`는 `esp8266/led_server/secrets.h`에서 설정한다. Pi 주소가 달라지면 펌웨어 설정을 확인한다. 저장소의 최신 작업자 코드는 기존 AE의 `poa`를 새 IP로 갱신하려 하지만 실제 장치에 올라간 버전과 성공 여부를 확인해야 한다. `AE-worker01`의 `poa`와 `alert` SUB의 `nu`를 조회해 실제 장치 주소가 반영됐는지 확인한다.
4. 브리지 목적지는 `BRIDGE_IN_BASE`다. Pi에서는 `systemctl cat safezone-bridge`로 `/etc/systemd/system/safezone-bridge.service.d/`의 적용 순서를 확인한다. 2026-11-20에는 마지막 `zzz-laptop74.conf`가 이전 주소 설정보다 우선했다. 노트북 IN 주소가 달라지면 현재 drop-in을 백업하고 실제 주소와 CSE 이름에 맞춰 갱신한 뒤 `daemon-reload`와 브리지 재시작이 필요하다. `BRIDGE_STATE`는 전달 위치를 기록하므로 원인 확인 없이 삭제하지 않는다.
5. MN의 상위 CSE 등록 주소는 브리지 목적지와 별도다. `systemctl cat tinyiot-mn`의 실제 실행 파일과 CSE 설정, 노트북 IN 등록 상태를 확인한다. Pi 빌드에서 원격 주소를 어디서 읽는지 확인하기 전에는 브리지 주소만 바꿔 Mcc 등록도 바뀐다고 가정하지 않는다.
6. 노트북 대시보드의 IN 주소와 포트 설정을 확인하고, 재연결 후 새 radar·events, 세 alert CNT, 각 ESP 알림과 화면의 실제 데이터 시각을 확인한다. 오래된 CIN이 남아 있을 수 있으므로 표시만으로 새 데이터가 들어왔다고 판단하지 않는다.

tinyIoT 소스 및 빌드 출처의 한계는 [tinyIoT 빌드 기록](../onem2m/tinyiot-patches/README.md)에 정리했다.
