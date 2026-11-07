#!/bin/bash
# 사용법: bash sub_alert_node.sh <ESP8266_IP>
CSE="${ONEM2M_CSE_BASE:-http://$(hostname -I | awk '{print $1}'):3000/TinyIoT-MN}"
ESP=$1
H=(-H "X-M2M-Origin: Cforklift01" -H "X-M2M-RVI: 3" -H "Accept: application/json")

# 기존 구독 삭제 (처음이면 에러가 나도 무시)
curl -s -X DELETE "$CSE/AE-forklift01/alert/sub-alert-node" -H "X-M2M-RI: s1" "${H[@]}"; echo

# 새 구독 (ty=23): alert에 새 데이터(net 3)가 생기면 ESP8266으로 알림
curl -s -X POST "$CSE/AE-forklift01/alert" -H "X-M2M-RI: s2" "${H[@]}" \
  -H "Content-Type: application/json;ty=23" \
  -d "{\"m2m:sub\":{\"rn\":\"sub-alert-node\",\"nu\":[\"http://192.168.219.104:80/notify\"],\"nct\":1,\"enc\":{\"net\":[3]}}}"; echo
