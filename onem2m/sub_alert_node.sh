#!/bin/bash
# 지게차 alert(AE-forklift01/alert)에 ESP8266 알림 구독을 만든다. ESP를 켤 때마다(IP가 바뀔 때) 다시 실행한다.
# 사용법: bash onem2m/sub_alert_node.sh <ESP IP> [구독 이름]
#   지게차 ESP:  bash onem2m/sub_alert_node.sh <FORKLIFT_ESP_IP>
#   작업자 ESP:  bash onem2m/sub_alert_node.sh <WORKER_ESP_IP> sub-worker01-forklift
# ESP IP는 ESP 시리얼 모니터(115200)의 "IP: ..." 줄에서 확인한다.
CSE="${ONEM2M_CSE_BASE:-http://127.0.0.1:3000/TinyIoT-MN}"
ESP=$1
RN=${2:-sub-alert-node}
[ -z "$ESP" ] && { echo "사용법: bash onem2m/sub_alert_node.sh <ESP IP> [구독 이름]"; exit 1; }
H=(-H "X-M2M-RVI: 3" -H "Accept: application/json")

# 응답 없는 ESP로 구독을 만들면 alert를 쓸 때마다 MN이 약 27초씩 멈춘다. 먼저 확인한다.
if ! curl -s -m 2 -o /dev/null "http://${ESP}:80/"; then
  echo "!! ${ESP}:80 응답 없음. ESP 전원·Wi-Fi(같은 핫스팟)·IP를 확인하세요. 구독을 만들지 않았습니다."
  exit 1
fi

# 같은 이름의 기존 구독 삭제 (없으면 에러가 나도 무시)
for O in Cforklift01 CAdmin; do
  curl -s -o /dev/null -X DELETE "$CSE/AE-forklift01/alert/$RN" -H "X-M2M-Origin: $O" -H "X-M2M-RI: d-$O" "${H[@]}"
done

# 새 구독 (ty=23): alert에 새 데이터(net 3)가 생기면 ESP8266으로 알림
curl -s -X POST "$CSE/AE-forklift01/alert" -H "X-M2M-Origin: Cforklift01" -H "X-M2M-RI: s2" "${H[@]}" \
  -H "Content-Type: application/json;ty=23" \
  -d "{\"m2m:sub\":{\"rn\":\"${RN}\",\"nu\":[\"http://${ESP}:80/notify\"],\"nct\":1,\"enc\":{\"net\":[3]}}}"; echo
