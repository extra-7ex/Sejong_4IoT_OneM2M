# oneM2M CSE 운영 절차

tinyIoT MN-CSE(Pi)와 IN-CSE 기동·점검·장애 대응 절차. 주소는 `<...>` 자리표시자로 적는다.
CSE 이름 전환은 [CSE 명명안](cse-naming.md), MQTT 규격은 [onem2m/mqtt.md](../onem2m/mqtt.md)를 따른다.

## 1. 구성

| CSE | 위치 | 포트 | `CSE_BASE_RI` | 서비스 |
|---|---|---|---|---|
| MN | Pi `~/tinyIoT` | 3000 (HTTP), MQTT on | `id-mn` | `tinyiot-mn` |
| IN (권장) | Pi `~/tinyIoT-in` | 3001 | `id-in` | `tinyiot-in-local` |
| IN (대안) | 노트북 WSL `~/tinyIoT` | 3000 | `id-in` | `tinyiot-in` + `forward_in.bat` |
| 브로커 | Pi Mosquitto | 1883 | - | `mosquitto` |

설정 예시: `onem2m/config.mn.example.h`, `onem2m/config.in.example.h`. 서비스 파일: `systemd/`.

## 2. 서비스 등록·제어

```bash
sudo cp systemd/tinyiot-mn.service systemd/tinyiot-in-local.service /etc/systemd/system/
sudo sed -i 's/<PI_USER>/실제계정/g' /etc/systemd/system/tinyiot-*.service
sudo systemctl daemon-reload
sudo systemctl enable --now tinyiot-in-local tinyiot-mn

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

## 5. Pi 내부 IN 배치

MN은 기동할 때 IN 등록에 실패하면 스스로 종료한다. IN이 노트북에 있으면 공유기나 노트북 IP가 바뀔 때마다 MN이 뜨지 않으므로, 시연용으로 IN을 같은 Pi의 3001 포트에 둔다.

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

## 6. 네트워크·IP가 바뀔 때

| 배치 | 바꿀 것 |
|---|---|
| Pi 내부 IN | MN `SERVER_IP`만 새 Pi IP로 (클라이언트 접근용). MN↔IN은 127.0.0.1이라 영향 없음 |
| 노트북 IN | MN `SERVER_IP`, `REMOTE_CSE_HOST`(노트북 IP), 노트북에서 `forward_in.bat` 재실행 |
| 공통 | 클라이언트의 `ONEM2M_CSE_BASE`, ESP의 브로커 주소, 구독 `nu` 주소 |

- 도서관 등 공용 Wi-Fi는 기기 간 통신을 막는 경우(AP 격리)가 많다. 휴대폰 핫스팟 등 개인 망을 쓴다.
- `.local` 이름이 풀리지 않으면 IP를 직접 쓴다.

## 7. 노트북 WSL IN (대안 배치)

WSL은 Windows와 다른 내부 IP(172.x)를 쓴다. Pi가 WSL의 IN에 닿으려면 Windows 포트포워딩이 필요하다.

1. WSL에서 `systemd/tinyiot-in.service` 등록 (`<WSL_USER>` 수정)
2. Windows에서 `onem2m/forward_in.bat`을 **관리자 권한으로 실행** (WSL IP 자동 감지, 방화벽 3000 허용)
3. Pi에서 `curl http://<NOTEBOOK_IP>:3000/TinyIoT ...`로 확인

WSL IP는 재부팅 때 바뀔 수 있으므로 부팅 후마다 2를 다시 실행한다.

## 8. 트러블슈팅

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
