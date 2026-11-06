#!/bin/bash
# 시험용 CSE에 접근 권한(ACP)을 준다 — 팀 setup_onem2m.sh 다음에 실행 (CLAUDE.md 2장 빈 연결 5).
#
# tinyIoT 기본 규칙은 "만든 AE(주인)만 접근"이라, 엔진(Criskengine)이 AE-forklift01/radar를 읽으면
# 403 originator has no privilege가 난다(2026-11-05 확인). 팀 스크립트에는 ACP가 없다 → 팀에 알리고, 시험은 이걸로 한다.
#   radar: 주인 Cforklift01 전부(63), 엔진·VisionAI는 읽기+찾기(RETRIEVE 2 + DISCOVERY 32 = 34)
#   alert: 주인 Cforklift01 전부, 엔진은 쓰기+읽기(CREATE 1 + RETRIEVE 2 = 3) — 팀 설계상 엔진이 alert에도 쓴다
#   fusedTracks: 주인 CVisionAI 전부, 엔진은 읽기+찾기(34) — AE-VisionAI·fusedTracks가 없으면 먼저 만든다(VisionAI도 시작할 때 만든다)
#
#   bash tools/setup_test_acp.sh                       # 기본 CSE http://127.0.0.1:3000/TinyIoT
#   bash tools/setup_test_acp.sh http://<IP>:3000/TinyIoT
CSE=${1:-http://127.0.0.1:3000/TinyIoT}
H=(-H "X-M2M-RVI: 3" -H "Accept: application/json")
ORIG=Cforklift01

req() {  # req <메서드> <경로> <ty> <JSON>   (originator = $ORIG)
  printf '%-6s %-40s ' "$1" "$2"
  curl -s -o /dev/null -w "%{http_code}\n" -X "$1" "$CSE$2" -H "X-M2M-Origin: $ORIG" "${H[@]}" -H "X-M2M-RI: acp$RANDOM" \
    -H "Content-Type: application/json;ty=$3" -d "$4"
}

acp() {  # acp <부모 AE> <이름> <다른 AE들(JSON 배열)> <acop>   — 주인($ORIG)은 전부(63)
  req POST "/$1" 1 "{\"m2m:acp\":{\"rn\":\"$2\",\"pv\":{\"acr\":[{\"acor\":[\"$ORIG\"],\"acop\":63},{\"acor\":$3,\"acop\":$4}]},\"pvs\":{\"acr\":[{\"acor\":[\"$ORIG\"],\"acop\":63}]}}}"
}

ORIG=Cforklift01
acp AE-forklift01 acp-radar '["Criskengine","CVisionAI"]' 34
acp AE-forklift01 acp-alert '["Criskengine"]' 3
req PUT /AE-forklift01/radar 3 '{"m2m:cnt":{"acpi":["TinyIoT/AE-forklift01/acp-radar"]}}'
req PUT /AE-forklift01/alert 3 '{"m2m:cnt":{"acpi":["TinyIoT/AE-forklift01/acp-alert"]}}'

ORIG=CVisionAI
req POST "" 2 '{"m2m:ae":{"rn":"AE-VisionAI","api":"NVisionAI","rr":true,"srv":["3"]}}'
req POST /AE-VisionAI 3 '{"m2m:cnt":{"rn":"fusedTracks","mni":100}}'
acp AE-VisionAI acp-fused '["Criskengine"]' 34
req PUT /AE-VisionAI/fusedTracks 3 '{"m2m:cnt":{"acpi":["TinyIoT/AE-VisionAI/acp-fused"]}}'
echo "(201 = 만듦, 409 = 이미 있음, 200 = 연결함)"
