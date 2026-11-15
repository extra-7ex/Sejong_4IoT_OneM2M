#!/bin/bash
# AE-forklift01/alert 구독을 MQTT 알림으로 만든다 (ESP: esp8266/alert_node_mqtt).
# tinyIoT는 nu=mqtt://<브로커>/<경로>로 알림을 토픽 /oneM2M/req/<CSE_BASE_RI>/<경로> 에 보낸다.
# ESP의 IP가 필요 없다. HTTP 판(sub_alert_node.sh)과 같은 이름 sub-alert-node를 쓰므로 둘 중 하나만 남는다.
#
# 사용법: bash onem2m/sub_alert_node_mqtt.sh [브로커 주소]   (기본 127.0.0.1 = MN과 같은 Pi의 Mosquitto)
#   ONEM2M_CSE_BASE로 CSE 주소를 바꿀 수 있다 (기본 http://<이 기기 IP>:3000/TinyIoT-MN)
CSE="${ONEM2M_CSE_BASE:-http://$(hostname -I | awk '{print $1}'):3000/TinyIoT-MN}"
BROKER=${1:-127.0.0.1}
NU="mqtt://$BROKER:1883/Calertnode/json"
H=(-H "X-M2M-Origin: Cforklift01" -H "X-M2M-RVI: 3" -H "Accept: application/json")

# 기존 구독 삭제 (처음이면 404가 나도 무시)
curl -s -o /dev/null -w "DELETE sub-alert-node -> %{http_code}\n" -X DELETE "$CSE/AE-forklift01/alert/sub-alert-node" -H "X-M2M-RI: sm1" "${H[@]}"

# 새 구독 (ty=23): alert에 새 데이터(net 3)가 생기면 MQTT로 알림
curl -s -X POST "$CSE/AE-forklift01/alert" -H "X-M2M-RI: sm2" "${H[@]}" \
  -H "Content-Type: application/json;ty=23" \
  -d "{\"m2m:sub\":{\"rn\":\"sub-alert-node\",\"nu\":[\"$NU\"],\"nct\":1,\"enc\":{\"net\":[3]}}}"; echo
echo "ESP 구독 토픽: /oneM2M/req/<CSE_BASE_RI>/Calertnode/json  (TinyIoT-MN이면 /oneM2M/req/tinyiot-mn/Calertnode/json)"
