# 4IoT_OneM2M
세종대학교_OneM2M_4Iot

1. 프로젝트 개요
1.1 배경
지게차와 크레인은 차체 구조상 사각지대가 넓어, 후진이나 선회 중 작업자와 부딪히거나 끼이는 사고가 반복된다. 기존 후방카메라와 경광등은 운전자를 보조할 뿐 작업자에게 직접 경고하지 않고, 장비가 스스로 멈추지도 않는다. UWB·BLE 태그 방식은 작업자가 장비를 착용해야 해서, 미착용이나 배터리 방전 시 보호 공백이 생긴다.
1.2 목표
목표
내용
무태그 감지
24GHz mmWave 레이더(HLK-LD2450)로 작업자를 착용 장비 없이 감지한다
예측형 판단
충돌까지 남은 시간(TTC)으로 위험도를 판정해 장비 자동 감속·정지와 작업자 경보를 수행한다
표준 상호운용성
모든 데이터를 oneM2M 표준 리소스로 관리해 관제·분석과 타사 장비 연동이 가능하게 한다


1.3. 구성도
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
계층
구성
역할
현장
레이더 노드 (ESP8266 #1 + LD2450)
표적 좌표·속도 수집, 로컬 인터락 판정, CSE 업로드
현장
장비 동작부 (Arduino + 모터 + LED)
장비 동력 표현, 상태별 감속·정지·표시
현장
작업자 경보기 (ESP8266 #2 + 부저)
작업 구역 내 작업자 경보
현장
카메라 노드 (웹캠)
움직임·사람 검출로 레이더 감지 보완
MEC
Raspberry Pi 4B
MN-CSE(tinyIoT), 위험 판단 엔진, AI 추론
클라우드
노트북 또는 대회 제공 플랫폼
IN-CSE, 이력 저장, 관제 대시보드
