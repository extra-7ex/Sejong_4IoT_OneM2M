#!/bin/bash
# 레이더 단독 흐름 한 번에 (Pi에서): 가짜 수신기 → 팀 엔진(수정 없음) → 레이더 업로더(sim)  (CLAUDE.md 13장)
#   sim 레이더 → tinyIoT AE-forklift01/radar → 엔진(~/riskengine) → AE-riskengine/events(+alert 예정) → 가짜 수신기(LED 대신)
#
# 먼저: bash tools/start_local_cse.sh(다른 창) → ONEM2M_CSE_BASE=http://127.0.0.1:3000/TinyIoT bash ~/Sejong_4IoT_OneM2M/onem2m/setup_onem2m.sh → bash tools/setup_test_acp.sh
#   bash tools/run_radar_flow.sh            # 40초 (시나리오 30초 한 바퀴 + 여유)
#   bash tools/run_radar_flow.sh 0          # Ctrl+C까지
# 로그: /dev/shm/flow/{receiver,engine,uploader}.log
cd "$(dirname "$0")/.." || exit 1
DUR=${1:-40}
CSE=${CSE_BASE:-http://127.0.0.1:3000}
ENGINE_DIR=${ENGINE_DIR:-$HOME/riskengine}
PY=.venv/bin/python
L=/dev/shm/flow
mkdir -p $L

cleanup() {
  [ -n "$ENG" ] && kill -TERM "$ENG" 2>/dev/null
  [ -n "$RCV" ] && kill -TERM "$RCV" 2>/dev/null       # 수신기는 끝날 때 구독을 지운다
  wait 2>/dev/null
}
trap cleanup EXIT
trap 'exit 130' INT TERM

$PY -m vision4iot.alert_receiver --config config.test.yaml --base-url "$CSE" > $L/receiver.log 2>&1 &
RCV=$!
sleep 2
(cd "$ENGINE_DIR" && ONEM2M_CSE_BASE="$CSE/TinyIoT" exec python3 -m engine.main --transport polling) > $L/engine.log 2>&1 &
ENG=$!
sleep 2
tail -n +1 -f $L/receiver.log &
TAIL=$!
if [ "$DUR" = 0 ]; then
  $PY -m vision4iot.radar_uploader --config config.test.yaml --base-url "$CSE" > $L/uploader.log 2>&1
else
  $PY -m vision4iot.radar_uploader --config config.test.yaml --base-url "$CSE" --duration "$DUR" > $L/uploader.log 2>&1
  sleep 2.5            # 업로더가 멈추면 엔진이 1초 뒤 UNKNOWN으로 바뀌는 것까지 본다
fi
kill $TAIL 2>/dev/null
echo "--- 업로더: $(tail -1 $L/uploader.log)"
