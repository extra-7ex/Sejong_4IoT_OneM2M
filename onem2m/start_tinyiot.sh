#!/bin/bash
# 현재 IP로 SERVER_IP 갱신 → 바뀌었으면 재빌드 → 서버 실행
cd ~/tinyIoT/source/server
IP=$(hostname -I | awk '{print $1}')
if ! grep -qE "#define\s+SERVER_IP\s+\"$IP\"" config.h; then
  echo "IP 변경 감지: $IP → 재빌드"
  sed -i -E "s/(#define\s+SERVER_IP\s+)\"[^\"]*\"/\1\"$IP\"/" config.h
  make clean && make
fi
./server