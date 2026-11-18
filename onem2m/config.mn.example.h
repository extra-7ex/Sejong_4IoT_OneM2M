// MN-CSE (Raspberry Pi) - tinyIoT source/server/config.h 에서 바꾼 매크로만 발췌한 예시
// <...> 는 자리표시자. 실제 IP, Wi-Fi, MQTT 계정은 저장소에 올리지 않는다.
// 수정 후 반드시 `make clean && make` (Makefile이 config.h 변경을 추적하지 않음).

#define SERVER_TYPE   MN_CSE
#define SERVER_IP     "<RPI_IP>"
#define SERVER_PORT   "3000"
#define CSE_BASE_NAME "<CSE_BASE_NAME>"      // 11/10 시험 당시 "TinyIoT-mn", 팀 기본값 "TinyIoT-MN" (docs/cse-naming.md)
#define CSE_BASE_RI   "id-mn"                // MQTT 토픽에 쓰이는 값

#if SERVER_TYPE == MN_CSE
#define REMOTE_CSE_ID    "id-in"             // 상위 IN의 CSE_BASE_RI
#define REMOTE_CSE_NAME  "TinyIoT"           // 상위 IN의 CSE_BASE_NAME
#define REMOTE_CSE_HOST  "127.0.0.1"         // Pi 내부 IN(권장). 노트북 IN이면 "<NOTEBOOK_IP>"
#define REMOTE_CSE_SP_ID "tinyiot.example.com"
#define REMOTE_CSE_PORT  3001                // Pi 내부 IN. 노트북 IN이면 3000
#endif

#define ALLOWED_REMOTE_CSE_ID "/id-in,/id-mn"

// Pi DB가 느려 IN 등록 응답이 3초를 넘긴 적이 있음 (기본 3 -> 10 권장, 아직 Pi에 미적용)
#define SOCKET_TIMEOUT 10

// MQTT는 MN에서만 켠다 (onem2m/mqtt.md)
#define ENABLE_MQTT
#define MQTT_HOST "127.0.0.1"
