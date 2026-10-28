# 4IoT_OneM2M
세종대학교_OneM2M_4Iot

```
forklift-safety-onem2m/
├─ README.md                 프로젝트 개요, 구성도, 실행 방법
├─ .gitignore
├─ docs/
│  ├─ architecture.md        시스템 구성도, 리소스 트리
│  ├─ data-format.md         컨테이너별 데이터 형식 
│  └─ runbook.md             작업 재개 절차
├─ onem2m/
│  ├─ setup_onem2m.sh        리소스 생성 스크립트
│  └─ demo.sh                시연 스크립트
├─ radar/                    담당: 지현태
│  ├─ README.md
│  ├─ ld2450.py
│  └─ proximity.py
├─ camera/                   담당: 박상희
│  ├─ README.md
│  └─ motion_detect.py
├─ engine/                   위험 판단 엔진
│  └─ README.md
└─ esp8266/                  엣지 컴퓨터
   └─ led_server/            담당: 지현태
      ├─ led_server.ino
      ├─ secrets.example.h
      └─ secrets.h       
```
