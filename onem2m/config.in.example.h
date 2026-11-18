// IN-CSE - tinyIoT source/server/config.h 에서 바꾼 매크로만 발췌한 예시
// 수정 후 반드시 `make clean && make`.
// 배치는 둘 중 하나를 고른다.

// 배치 A: Pi 내부 IN (권장, 시연용). 공유기·노트북과 무관하게 MN과 함께 뜬다.
//   MN과 같은 Pi에서 별도 복사본(예: ~/tinyIoT-in)을 포트 3001로 실행한다.
#define SERVER_TYPE   IN_CSE
#define SERVER_IP     "127.0.0.1"
#define SERVER_PORT   "3001"                 // MN(3000)과 겹치지 않게
#define CSE_BASE_NAME "TinyIoT"
#define CSE_BASE_RI   "id-in"
#define ALLOWED_REMOTE_CSE_ID "/id-in,/id-mn"
// MQTT는 끈 상태로 둔다: // #define ENABLE_MQTT
//   (MN과 같은 브로커에 같은 ClientID "TinyIoT"로 붙으면 서로 연결을 끊음)

// 배치 B: 노트북 WSL IN
// #define SERVER_IP   "0.0.0.0"
// #define SERVER_PORT "3000"
//   MN의 REMOTE_CSE_HOST = "<NOTEBOOK_IP>", REMOTE_CSE_PORT = 3000
//   Windows 포트포워딩 필요 (onem2m/forward_in.bat, docs/runbook.md)
