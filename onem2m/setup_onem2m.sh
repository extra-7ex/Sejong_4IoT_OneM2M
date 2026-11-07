#!/bin/bash
CSE="${ONEM2M_CSE_BASE:-http://$(hostname -I | awk '{print $1}'):3000/TinyIoT-MN}"

post() {  # 사용법: post <경로> <ty> <Origin> <JSON>
  curl -s -X POST "$CSE$1" \
    -H "X-M2M-Origin: $3" -H "X-M2M-RI: req$RANDOM" -H "X-M2M-RVI: 3" \
    -H "Content-Type: application/json;ty=$2" -H "Accept: application/json" \
    -d "$4"
  echo
}

# AE: 앱·장치 등록 (ty=2)
post ""  2 Cforklift01  '{"m2m:ae":{"rn":"AE-forklift01","api":"Nforklift","rr":true,"srv":["3"]}}'
post ""  2 Czonealarm01 '{"m2m:ae":{"rn":"AE-zonealarm01","api":"Nzonealarm","rr":true,"srv":["3"]}}'
post ""  2 Criskengine  '{"m2m:ae":{"rn":"AE-riskengine","api":"Nriskengine","rr":true,"srv":["3"]}}'
post ""  2 Ccamera01    '{"m2m:ae":{"rn":"AE-camera01","api":"Ncamera","rr":true,"srv":["3"]}}'

# CNT: 데이터 컨테이너 (ty=3), mni = 최대 보관 개수
post /AE-forklift01  3 Cforklift01  '{"m2m:cnt":{"rn":"radar","mni":100}}'
post /AE-forklift01  3 Cforklift01  '{"m2m:cnt":{"rn":"alert","mni":20}}'
post /AE-zonealarm01 3 Czonealarm01 '{"m2m:cnt":{"rn":"alert","mni":20}}'
post /AE-riskengine  3 Criskengine  '{"m2m:cnt":{"rn":"events","mni":100}}'
post /AE-camera01    3 Ccamera01    '{"m2m:cnt":{"rn":"detect","mni":100}}'
