#!/bin/bash
# 집 시험용 tinyIoT 실행 (Pi에서). 팀의 ~/tinyIoT는 건드리지 않는다 (CLAUDE.md 11장).
#
# 팀 Pi의 ~/tinyIoT는 MN-CSE "TinyIoT-mn"(IN-CSE는 팀 노트북)으로 설정돼 있어
# IN이 없는 곳에서는 시험할 수 없다. 그래서 복사본 ~/tinyIoT-local을 만들어
# 원본 기본값(IN-CSE "TinyIoT")에 SQLite로 돌린다 → 팀 깃허브 스크립트의 /TinyIoT 주소와 같다.
#
#   bash tools/start_local_cse.sh            # 처음엔 복사·빌드(몇 분), 다음부턴 바로 실행
#   주소: http://<Pi IP>:3000/TinyIoT        (끄기: Ctrl+C)
#
# DB(data.db)는 RAM 디스크(/dev/shm)에 둔다: 이 Pi의 SD카드는 동기화 쓰기 한 번에 약 340ms라(2026-11-05 측정)
# SQLite에 CIN 하나 커밋하는 데 약 1.35초 걸린다 → 레이더 10Hz 불가, 엔진 UNKNOWN. RAM이면 수 ms.
# 대신 재부팅·재시작하면 리소스가 사라진다 → 실행 후 팀 onem2m/setup_onem2m.sh를 다시 돌린다.
# SD카드에 두려면 CSE_RUN_DIR=<SD카드 폴더>.
set -e
SRC=${TEAM_TINYIOT:-$HOME/tinyIoT}
DST=${LOCAL_TINYIOT:-$HOME/tinyIoT-local}
RUN_DIR=${CSE_RUN_DIR:-/dev/shm/tinyIoT-local}

if systemctl is-active -q tinyiot-mn 2>/dev/null; then
  echo "팀 tinyiot-mn 서비스가 3000번 포트를 쓰는 중이에요. 먼저 끄세요: sudo systemctl stop tinyiot-mn" >&2
  exit 1
fi

if [ ! -d "$DST" ]; then
  echo "처음 실행: $SRC → $DST 복사 (팀 원본은 그대로)"
  cp -a "$SRC" "$DST"
  cd "$DST/source/server"
  git -C "$DST" checkout -- source/server/config.h          # 원본 기본값: IN-CSE, TinyIoT, MQTT 꺼짐
  sed -i -E 's|^#define DB_TYPE DB_POSTGRESQL|// &|; s|^// *#define DB_TYPE DB_SQLITE|#define DB_TYPE DB_SQLITE|' config.h
  rm -f data.db                                             # 팀 데이터는 가져오지 않는다
  FORCE_BUILD=1
fi

cd "$DST/source/server"
IP=$(hostname -I | awk '{print $1}')
if [ -n "$FORCE_BUILD" ] || ! grep -qE "^#define\s+SERVER_IP\s+\"$IP\"" config.h; then
  echo "SERVER_IP=$IP 로 빌드"
  sed -i -E "s/^(#define\s+SERVER_IP\s+)\"[^\"]*\"/\1\"$IP\"/" config.h
  make clean >/dev/null && make -j4 >/dev/null
fi

mkdir -p "$RUN_DIR"
[ -d sdt_definitions ] && ln -sfn "$PWD/sdt_definitions" "$RUN_DIR/sdt_definitions"   # 서버가 ./sdt_definitions를 읽는다
echo "tinyIoT(시험용) 실행: http://$IP:3000/TinyIoT  (DB: $RUN_DIR/data.db)"
[ -e "$RUN_DIR/data.db" ] || echo "  새 DB → 리소스 만들기: bash ~/Sejong_4IoT_OneM2M/onem2m/setup_onem2m.sh"
cd "$RUN_DIR"
exec "$DST/source/server/server"
