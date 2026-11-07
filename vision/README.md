# 4iot VisionAI

영상·AI 파트. 자세한 내용은 CLAUDE.md 참고.

## 설치 (노트북, Windows)

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt -e .
```

## 실행

```
.venv\Scripts\python -m vision4iot.main                 # 화면에 박스·관절·id·FPS, q로 종료
.venv\Scripts\python -m vision4iot.main --headless      # 화면 없이 1초마다 FPS (Ctrl+C로 종료)
.venv\Scripts\python -m vision4iot.main --source data\walk.mp4
```

처음 실행하면 `yolo11n-pose.pt`(약 6MB)를 자동으로 내려받는다.

## 확인

```
.venv\Scripts\python tools\check_webcam.py
.venv\Scripts\python -m pytest
```

## 바닥 보정 (호모그래피)

바닥에 테이프로 6점 이상 표시하고 실제 좌표(m)를 잰다. 원점 = 지게차 후면 중앙 바닥, x 오른쪽 +, y 멀어지는 쪽 +.

```
.venv\Scripts\python tools\calibrate.py                          # 실시간 → 스페이스로 멈춤 → 클릭 + 터미널에 "x y"
.venv\Scripts\python tools\calibrate.py --image calib\pi.jpg     # 저장한 사진으로
python tools/calibrate.py --grab calib/pi.jpg                    # Pi: 사진만 저장 (화면 없이)
python tools/calibrate.py --image calib/pi.jpg --points calib/points.csv   # Pi: 클릭 없이 u,v,x,y 파일로
```

결과: `calib/H.json`(H, 날짜, 재투영 오차) + `calib/H_check.jpg`(0.5m 바닥 격자 — 바닥에 딱 붙어 보여야 함).

## Pi 4 (Raspberry Pi OS Lite 64-bit, Trixie, Python 3.13) — 2026-11-06 기준

카메라는 로지텍 C270(USB, `/dev/video0`). 전원은 5V 3A (휴대폰 충전기면 전압 부족으로 느려짐).

설치(한 번, 이미 되어 있음):
```
sudo apt install -y python3-venv python3-dev libgl1 libglib2.0-0 git
python3 -m venv .venv
.venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # CPU판 먼저 (안 그러면 NVIDIA 라이브러리를 받다 끊김)
.venv/bin/pip install -r requirements.txt ncnn -e .
.venv/bin/yolo export model=yolo11n-pose.pt format=ncnn imgsz=320   # → yolo11n-pose_ncnn_model/
```

실행 — 레이더는 tinyIoT `AE-forklift01/radar`에서 읽고, 결과는 `AE-VisionAI/fusedTracks`에 올린다:
```
.venv/bin/python -m vision4iot.main --config config.pi.yaml --radar onem2m --output onem2m --base-url http://127.0.0.1:3000
.venv/bin/python -m vision4iot.main --config config.pi.yaml --radar sim     # 레이더 없이 (카메라 위치로 가짜 레이더), 결과는 화면 출력
```
팀 제안 기본 CSE 이름은 `TinyIoT-MN`이다. Pi에 실제 적용했는지 먼저 확인하고, 다르면 `config.local.yaml`의 `onem2m: {cse_name: ...}`에 실제 이름을 지정한다. [전환 안내](../docs/cse-naming.md)

카메라 위치 맞추기 → 바닥 보정(카메라를 옮기면 다시):
```
.venv/bin/python tools/live_view.py          # 브라우저 http://4Iot.local:8080, 바닥/벽 경계를 초록 선 근처로. 다 맞추면 Ctrl+C
.venv/bin/python tools/calibrate.py --config config.pi.yaml --grab calib/site.jpg     # 테이프 점 6개 붙인 뒤 사진
# 노트북: scp로 가져와 --image calib/site.jpg 로 점 클릭 (또는 u,v,x,y 점 파일로 --points) → calib/H.json을 Pi로
```
지금 `calib/H.json`은 상희 집 임시 설치(약 1 m 높이) 기준 — 대회장에서 다시 한다. 예시 점 파일: `calib/points_c270.csv`.

시험용 도구(레이더·장비가 없을 때): `tools/start_local_cse.sh`(시험용 tinyIoT, 팀 설정과 포트 3000이 겹침),
`tools/setup_test_acp.sh`(접근 권한), `tools/run_radar_flow.sh`(가짜 수신기 + 팀 엔진 `~/riskengine` + 레이더 업로더 sim).
