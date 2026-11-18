#!/bin/bash
# SafeZone 시연 서비스를 /etc/systemd/system에 설치한다 (켜거나 자동 시작 등록은 하지 않음).
#   sudo bash systemd/install.sh <PI_USER> [VisionAI 폴더] [VisionAI python]
# 예 (팀 Pi): sudo bash systemd/install.sh hyuntae /home/user/vision4iot
set -euo pipefail
U=${1:?"사용법: sudo bash systemd/install.sh <PI_USER> [VISION_DIR] [VISION_PYTHON]"}
REPO=$(cd "$(dirname "$0")/.." && pwd)
VDIR=${2:-$REPO/vision}
VPY=${3:-$VDIR/.venv/bin/python}
[ -x "$VPY" ] || echo "경고: $VPY 가 없습니다. safezone-vision은 실행에 실패합니다."
[ -e "$VDIR/config.pi.yaml" ] || echo "경고: $VDIR/config.pi.yaml 이 없습니다."
for f in "$REPO"/systemd/safezone*.service "$REPO"/systemd/safezone.target; do
  sed -e "s#/home/<PI_USER>/Sejong_4IoT_OneM2M#$REPO#g" -e "s#<PI_USER>#$U#g" \
      -e "s#<VISION_DIR>#$VDIR#g" -e "s#<VISION_PYTHON>#$VPY#g" "$f" > "/etc/systemd/system/$(basename "$f")"
  echo "설치: /etc/systemd/system/$(basename "$f")"
done
systemctl daemon-reload
cat <<MSG

다음 단계 (시연방법.md의 'D. 서비스로 켜기'):
  레이더 하나 고르기:  sudo systemctl enable safezone-radar      (실제 LD2450)
                       sudo systemctl enable safezone-sim-radar  (가상 레이더)
  나머지 등록:         sudo systemctl enable safezone-engine safezone-bridge safezone-dashboard safezone-ipe safezone-vision safezone.target
  전체 켜기/끄기:      sudo systemctl start safezone.target / sudo systemctl stop safezone.target
MSG
