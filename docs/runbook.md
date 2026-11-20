# oneM2M CSE 운영 절차

tinyIoT MN-CSE(Pi)와 시연용 노트북 IN-CSE의 기동·점검·장애 대응 절차. 실제 주소는 기록하지 않고 `<...>` 자리표시자로 적는다.
CSE 이름 전환은 [CSE 명명안](cse-naming.md), MQTT 규격은 [onem2m/mqtt.md](../onem2m/mqtt.md)를 따른다.
2026-11-20 Pi에서 확인한 전체 배치와 재현 한계는 [배포 및 운영 기록](deployment.md), 실제 요청 흐름은 [아키텍처](architecture.md)를 참고한다.

## 1. 구성

| CSE | 위치 | 포트 | `CSE_BASE_RI` | 서비스 |
|---|---|---|---|---|
| MN | Pi `~/tinyIoT` | 3000 (HTTP), MQTT on | `id-mn` | `tinyiot-mn` |
| IN (시연) | 노트북 Docker | Docker publish 설정에 따름 | `id-in` | 노트북 IN-CSE 컨테이너 |
| IN (대안 시험) | Pi `~/tinyIoT-in` | 3001 | `id-in` | `tinyiot-in-local` |
| 브로커 | Pi Mosquitto | 1883 | - | `mosquitto` |

설정 예시: `onem2m/config.mn.example.h`, `onem2m/config.in.example.h`. 서비스 파일: `systemd/`.

## 2. 서비스 등록·제어

```bash
sudo cp systemd/tinyiot-mn.service systemd/tinyiot-in-local.service /etc/systemd/system/
sudo sed -i 's/<PI_USER>/실제계정/g' /etc/systemd/system/tinyiot-*.service
sudo systemctl daemon-reload
sudo systemctl enable --now tinyiot-mn

systemctl status tinyiot-mn --no-pager      # 상태
journalctl -u tinyiot-mn -n 50 --no-pager   # 로그
sudo systemctl restart tinyiot-mn           # 재시작
ss -tln | grep -E '3000|3001|1883'          # 포트 확인
```

`tinyIoT` 폴더 소유자와 로그인 계정이 다르면 `config.h` 수정·빌드에 `sudo`가 필요하다.

## 3. 설정 변경 후 재빌드

```bash
cd ~/tinyIoT/source/server
make clean && make          # config.h 변경은 make clean 없이 반영되지 않음
sudo systemctl restart tinyiot-mn
```

Pi에서 빌드는 1~2분 걸린다.

## 4. 기동 확인

```bash
# CSEBase 조회 (rn, csi, ri 기록)
curl -s "http://127.0.0.1:3000/<CSE_BASE_NAME>" \
  -H "X-M2M-Origin: CAdmin" -H "X-M2M-RI: chk1" -H "X-M2M-RVI: 3" -H "Accept: application/json"

# MN 로그에서 IN 등록·MQTT 구독 확인
journalctl -u tinyiot-mn -n 80 --no-pager | grep -iE "registration|mqtt"
```

정상이면 `Remote CSE registration check: 200`과 `MQTT Subscribe Success` 4줄이 보인다.

## 5. Pi 내부 IN 배치 (대안 시험)

시연 구성은 노트북 Docker IN-CSE를 사용한다. Pi 내부 IN은 노트북 연결과 분리해 확인할 때만 쓰는 대안이다. MN은 기동할 때 상위 IN 등록에 실패하면 스스로 종료한다.

```bash
cp -r ~/tinyIoT ~/tinyIoT-in
cd ~/tinyIoT-in/source/server
rm -f data.db                       # 새 DB로 시작
# config.h를 onem2m/config.in.example.h 배치 A 값으로 수정 (SERVER_IP 127.0.0.1, PORT 3001, CSE_BASE_RI id-in, ENABLE_MQTT 끔)
make clean && make
sudo systemctl enable --now tinyiot-in-local

# MN이 Pi 내부 IN을 보도록 수정 후 재빌드
#   REMOTE_CSE_HOST "127.0.0.1", REMOTE_CSE_PORT 3001
```

## 6. 네트워크·주소가 바뀔 때

| 배치 | 바꿀 것 |
|---|---|
| Pi 주소 변경 | MN 설정의 `SERVER_IP`, worker `secrets.h`의 `CSE_HOST`, 노트북 dashboard의 `DASH_CSE_BASE`를 새 Pi 주소로 바꾼다. MN은 재빌드·재시작, worker 펌웨어는 재빌드·업로드, dashboard는 재시작 |
| 노트북 IN 주소 변경 | MN 설정의 `REMOTE_CSE_HOST/PORT`를 갱신해 MN 재빌드·재시작. 브리지의 `BRIDGE_IN_BASE`와 노트북 대시보드의 `DASH_IN_BASE`도 새 IN 주소로 바꾸고 각각 재시작 |
| 지게차 ESP 주소 변경 | ESP 시리얼 로그의 IP를 확인해 `bash onem2m/sub_alert_node.sh <ESP_IP>`를 다시 실행 |
| worker AE 재등록 | 새 worker alert CNT RI를 확인하고 `grp-safezone-alarms`의 `mid` 참조를 갱신한 뒤 fan-out과 알림을 확인 |
| 공통 | 클라이언트의 CSE 주소와 DHCP 주소 예약 여부를 실제 네트워크에서 확인. 비밀번호와 실주소는 저장소에 기록하지 않음 |

- 도서관 등 공용 Wi-Fi는 기기 간 통신을 막는 경우(AP 격리)가 많다. 휴대폰 핫스팟 등 개인 망을 쓴다.
- `.local` 이름이 풀리지 않으면 IP를 직접 쓴다.

## 7. ESP 연결 설정과 주소 갱신

### Worker ESP

1. `esp8266/led_server/secrets.example.h`를 같은 폴더의 `secrets.h`로 복사한다. `secrets.h`는 `.gitignore` 대상이므로 개인 Wi-Fi 정보와 장비 주소는 그 파일에만 쓴다.
2. Wi-Fi 이름·비밀번호와 `CSE_HOST=http://<PI_IP>:3000`을 설정한다. Pi 주소가 바뀌면 `CSE_HOST`를 바꾸고 worker 펌웨어를 다시 빌드·업로드한다.
3. 부팅 시 worker AE가 현재 ESP IP를 `poa`로 등록한다. 재등록으로 AE/alert CNT가 새로 만들어졌다면 새 alert RI를 확인해 그룹 `mid`를 갱신한다.

### Forklift motor ESP

이 ESP는 HTTP `/notify`를 열며, IP를 AE에 등록하지 않는다. Pi에서 ESP 시리얼 로그의 `IP: ...`를 확인한 뒤 아래 스크립트로 `AE-forklift01/alert` SUB의 `nu`를 갱신한다. 스크립트는 기존 같은 이름의 SUB를 삭제하고 다시 만든다.

```bash
bash onem2m/sub_alert_node.sh <ESP_IP>
```

두 ESP의 Wi-Fi 정보는 펌웨어의 무시 목록(`.gitignore`) 대상 `secrets.h`에만 둔다. `secrets.example.h`에는 자리표시자만 유지한다.

## 8. 노트북 WSL IN (대안 배치)

WSL은 Windows와 다른 내부 IP(172.x)를 쓴다. Pi가 WSL의 IN에 닿으려면 Windows 포트포워딩이 필요하다.

1. WSL에서 `systemd/tinyiot-in.service` 등록 (`<WSL_USER>` 수정)
2. Windows에서 `onem2m/forward_in.bat`을 **관리자 권한으로 실행** (WSL IP 자동 감지, 방화벽 3000 허용)
3. Pi에서 `curl http://<NOTEBOOK_IP>:3000/TinyIoT ...`로 확인

WSL IP는 재부팅 때 바뀔 수 있으므로 부팅 후마다 2를 다시 실행한다.

## 9. 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| MN 서비스가 `inactive (dead)` | IN 등록 실패로 종료 (IN 주소가 옛 IP, IN 미기동) | IN 상태 확인, `REMOTE_CSE_HOST/PORT` 확인 후 재빌드 |
| IN 등록이 간헐적으로 실패 | Pi DB가 느려 응답이 `SOCKET_TIMEOUT`(기본 3초)을 넘김 | `SOCKET_TIMEOUT 10`으로 재빌드 |
| config를 바꿨는데 반영 안 됨 | Makefile이 `config.h`를 추적하지 않음 | `make clean && make` |
| `bind() error: Address already in use` | 이전 프로세스가 포트를 잡고 있음 | `sudo ss -tlnp \| grep 3000`으로 PID 확인 후 그 프로세스만 종료. `pkill -f server`처럼 넓은 패턴은 VS Code 원격 서버까지 죽임 |
| MQTT 요청에 응답 없음 | 브로커 미기동, `ENABLE_MQTT` 꺼짐, 토픽 cse-ri 불일치 | `systemctl status mosquitto`, 기동 로그의 구독 토픽 확인 |
| MQTT `Invalid Request` | `m2m:rqp` 래퍼 사용 | 평평한 JSON으로 ([mqtt.md §3](../onem2m/mqtt.md)) |
| MQTT `rsc:4004` | `to` 앞 슬래시 | `to`를 CSEBase 이름부터 |
| CIN 생성 권한 오류 | `fr`이 AE를 만든 originator와 다름 | 같은 originator 사용, 다른 AE는 ACP 구성 |

## 10. MEC IPE 상태 기록

Pi의 운영 MEC IPE는 MEC011에서 Vision 서비스를 발견하고 등록된 oneM2M 주소의 최신 `fusedTracks`와 `cam_ok`를 확인해 MN-CSE에 데이터 상태를 기록한다. `ACTIVE`인 서비스 등록도 데이터가 오래되면 데이터 상태는 `INACTIVE`일 수 있다. VisionAI를 잠시 실행한 시험에서 데이터 상태가 `INACTIVE → ACTIVE`로 바뀌었고, 시험 후 VisionAI를 다시 중지했다.

주의: 현재 GitHub 제출 브랜치의 `onem2m/mec_ipe.py`는 Pi에 적용된 discovery 변경을 아직 포함하지 않는다. 아래 저장소 명령만 다시 실행해도 운영 discovery 기능이 배포되는 것은 아니다. 코드 브랜치가 저장소에 동기화된 뒤 설치·재시작 절차를 갱신한다.

```bash
# 저장소 루트에서 (Pi)
python3 -m onem2m.mec_ipe --once      # 한 번 확인·기록
python3 -m onem2m.mec_ipe             # 계속 실행
# 상태 확인
curl -s -H 'X-M2M-Origin: CAdmin' -H 'X-M2M-RI: chk' -H 'X-M2M-RVI: 3' -H 'Accept: application/json' \
  http://127.0.0.1:3000/TinyIoT-MN/AE-mecIPE/MecServices/safezone-vision/status/la
```

- 기록 위치: `AE-mecIPE/MecServices/<서비스>/status`. 상태가 바뀔 때와 10초마다 CIN을 쓴다. `la`의 `ts`가 30초 넘게 오래되면 IPE가 멈춘 것으로 보고 UNKNOWN으로 다룬다.
- 다른 서비스: `IPE_SERVICE=<이름> IPE_PROBE=http://<주소>/health` (2xx면 성공) 또는 `IPE_PROBE=cin:/<AE>/<CNT>/la`.
- MEC011 설정: `IPE_MEC_BASE`는 조회할 등록부, `IPE_MEC_SERVICE`는 찾을 서비스 이름, `IPE_DISCOVERY_CSE_BASE`는 발견 주소를 제한할 CSE다. 허용 CSE 값을 생략하면 `IPE_MN_BASE`를 사용한다. 현재 서비스 엔트리는 VisionAI의 실제 `fusedTracks` 주소로 수동 등록했다. 중복 서비스 이름은 임의 선택하지 않고 허용 CSE 밖 주소는 사용하지 않는다. 데이터 stale이면 `INACTIVE`, 새 데이터가 확인되면 `ACTIVE`로 쓴다. 발견 코드는 운영 Pi IPE에 적용됐지만 소스 브랜치 `codex/mec011-live-discovery`는 아직 GitHub에 push되지 않았다. 해당 브랜치의 단위 시험 17개 통과 보고가 있다. 원격 CSE 조회와 자동 서비스 등록·주소 갱신, 여러 서비스 중 위치·부하 기반 선택은 검증·구현하지 않았다.
- 주요 환경 변수: `IPE_PERIOD_S`(1.0), `IPE_FAIL_N`(3), `IPE_MAX_AGE_S`(2.0), `IPE_HEARTBEAT_S`(10), `IPE_READ_ORIGIN`(CAdmin), `IPE_ORIGIN`(CmecIPE).
- 시험: `python3 -m unittest onem2m.test_mec_ipe`
- Pi 시험(2026-11-18, 실제 MN-CSE, `bench_bus.mp4` 녹화 영상으로 돌린 실제 VisionAI 약 5 FPS): 꺼진 상태로 시작하면 2초 뒤 INACTIVE, VisionAI 시작 후 약 10초(모델 로딩 포함) 뒤 ACTIVE. VisionAI를 Ctrl+C로 멈추면 마지막 프레임 4.2–4.7초 뒤 INACTIVE, 다시 켜면 9.7초 뒤 ACTIVE. 같은 Pi에서 VisionAI를 두 개 돌려 약 1.6 FPS로 떨어졌을 때 잘못된 INACTIVE가 1초 동안 한 번 나왔으므로, 프레임이 2초 넘게 끊기는 환경이면 `IPE_MAX_AGE_S`를 늘린다.

### MEC011에서 Vision 데이터 endpoint 발견하기 (선택)

기본 `IPE_PROBE=cin:/AE-VisionAI/fusedTracks/la`는 MN-CSE 주소를 알고 직접 조회한다. MEC011을 경유하려면 Vision 데이터 제공 서비스가 먼저 MEC 서비스 등록부에 등록되어 있어야 한다. `mec_ipe`는 서비스 자체를 등록하지 않는다.

`IPE_PROBE=mec-cin`으로 바꾸면 IPE는 `IPE_MEC_BASE`의 MEC011 `/services?ser_name=...` 조회로 서비스를 찾고, `ACTIVE` 상태와 등록된 endpoint를 확인한 뒤 그 주소로 최신 CIN을 조회한다. endpoint는 `IPE_DISCOVERY_CSE_BASE`에 지정한 CSE 아래의 `/la` URI여야 하며, 비워두면 `IPE_MN_BASE`를 사용한다. 원격 CSE 사용 시 주소와 조회 권한을 미리 설정한다. 중복된 서비스 이름이나 허용한 주소 밖의 endpoint는 사용하지 않는다. MEC 등록부를 읽지 못하면 판정을 보류한다.

IPE가 쓴 `MecServices/<서비스>/status`는 현재 RiskEngine 입력으로 연결되어 있지 않다. MEC 발견 결과가 위험 판정에도 영향을 주게 하려면, 후속으로 엔진이 이 oneM2M 상태를 읽고 `ACTIVE`이며 상태 CIN이 신선할 때만 Vision 조언을 허용하도록 연결한다. 이때 레이더 단독 판정은 계속 유효하게 둔다.

```bash
IPE_MEC_BASE=http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1 \
IPE_MEC_SERVICE=<MEC에 등록된 서비스 이름> \
IPE_PROBE=mec-cin \
python3 -m onem2m.mec_ipe --once
```

위 주소는 같은 Pi에서 실행하는 Host A 시험 스택의 로컬 API 예시다. 다른 배치에서는 해당 플랫폼이 제공한 API root를 사용한다. `IPE_MEC_UPDATE`는 기본값 `0`으로 둔다. 이 기능은 MEC 서비스 상태를 자동 갱신하지 않으며, `ACTIVE` 표기만으로 최신 데이터가 있다고 보지 않는다. 실제 `fusedTracks` 데이터의 `ts`와 `cam_ok`를 계속 검사한다.

### Pi ARM64 MEC011 discovery 시험 (2026-11-20)

- Pi의 기존 MEC ARM64 컨테이너 네 개를 재시작했고, 로컬 MEC API와 모의 Vision 응답을 확인했다. 이미지 재빌드나 Redis 데이터 삭제는 하지 않았다.
- MEC 시험 앱 아래 `safezone-vision-cin-trial`을 별도 등록했다. endpoint는 실제 Pi MN-CSE의 `http://127.0.0.1:3000/TinyIoT-MN/AE-VisionAI/fusedTracks/la`였다.
- 변경한 IPE 파일을 Pi `/tmp`에서 `--once`로 실행하고 `AE-mecIPE-discovery-trial`에 상태 CIN을 썼다. 확인값은 `probe=mec-cin`, `state=ACTIVE`, `registry_state=ACTIVE`였다. 이는 운영 `safezone-ipe` 설정이나 서비스 코드를 전환한 결과가 아니다.
- VisionAI는 실제 카메라·레이더 입력으로 잠시 실행해 `cam_ok=true`, 표적 0개, 약 2.1 FPS를 발행했다. 약 82°C에 도달해 중지했고, 온도는 이후 약 65°C로 내려갔다. 시험 상태 CIN 기록은 VisionAI를 중지한 뒤 수행했으므로 시험 실행에서만 `IPE_MAX_AGE_S=600`을 사용했다. 따라서 이 기록의 `fresh` 판정은 기본 2초 신선도 검증으로 해석하면 안 된다.
- 이후 운영 `safezone-ipe`에 별도 파일과 systemd drop-in으로 `mec-cin`을 적용했다. 실제 VisionAI를 잠깐 실행하자 발견한 CIN이 최신으로 갱신되면서 IPE가 INACTIVE에서 ACTIVE로 바뀌었다. 약 2.1 FPS 상태에서 2초 신선도 기준을 잠깐 넘어 INACTIVE와 ACTIVE로 한 차례 흔들렸다. 시험 후 Vision은 중지했다.
- MEC 등록은 시험용 앱 아래 수동으로 만들었다. 실제 Vision 앱의 자동 등록, 여러 서비스 선택, MEC 상태 자동 갱신과 장시간 안정성은 미검증이다. 현재 설정과 복구 위치는 [Pi 운영 상태](pi-operating-state.md)를 참고한다.
