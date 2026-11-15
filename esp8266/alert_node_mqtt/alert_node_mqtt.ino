// alert 알림을 oneM2M MQTT 바인딩으로 받는 ESP8266 경보 노드.
// HTTP 판(led_server/alert_node.ino)과 하는 일은 같다: alert의 level이 warn·danger면 LED를 켜고 아니면 끈다.
// 차이: ESP가 웹서버를 열지 않고 Pi의 MQTT 브로커에 접속해 기다린다 → CSE가 ESP의 IP를 알 필요가 없다.
//
// CSE 쪽 구독: onem2m/sub_alert_node_mqtt.sh (nu = mqtt://127.0.0.1:1883/Calertnode/json)
// tinyIoT는 이 구독의 알림을 토픽 /oneM2M/req/<CSE_BASE_RI>/Calertnode/json 으로 보낸다(2026-11-14 Pi 실측).
// 알림 본문은 HTTP와 같은 {"m2m:sgn": {...}} 이다.
//
// 필요 라이브러리: PubSubClient (Nick O'Leary), ArduinoJson 7
#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "secrets.h"   // WIFI_SSID, WIFI_PASS, MQTT_HOST (secrets.example.h 참고)

#ifndef MQTT_PORT
#define MQTT_PORT 1883
#endif
#ifndef CSE_RI
#define CSE_RI "tinyiot-mn"          // MN의 CSE_BASE_RI
#endif
#define NOTIFY_TARGET "Calertnode"   // 구독 nu의 경로와 같아야 함

const char *TOPIC = "/oneM2M/req/" CSE_RI "/" NOTIFY_TARGET "/json";

WiFiClient net;
PubSubClient mqtt(net);

void setLed(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); }  // LOW가 켜짐

void onMessage(char *topic, byte *payload, unsigned int len) {
  Serial.printf("수신 %u바이트: %.*s\n", len, (int)(len > 300 ? 300 : len), (const char *)payload);
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  JsonVariant sgn = doc["m2m:sgn"];
  if (sgn.isNull()) sgn = doc["pc"]["m2m:sgn"];   // 요청 형식으로 감싸 오는 경우도 처리
  if (sgn["vrq"] | false) return;                  // 구독 확인 요청: 할 일 없음
  JsonVariant cin = sgn["nev"]["rep"]["m2m:cin"];
  if (cin.isNull()) return;                        // 새 데이터 알림이 아니면 무시

  JsonVariant con = cin["con"];
  String level;
  if (con.is<const char *>()) {                    // con이 문자열로 온 경우
    JsonDocument c;
    deserializeJson(c, con.as<const char *>());
    level = c["level"] | "";
  } else {
    level = con["level"] | "";
  }
  Serial.println("level = " + level);
  setLed(level == "danger" || level == "warn");
}

void connectMqtt() {
  while (!mqtt.connected()) {
    String id = "Calertnode-" + String(ESP.getChipId(), HEX);   // 장치마다 다른 ID
    Serial.print("MQTT 연결 중... ");
    if (mqtt.connect(id.c_str())) {
      mqtt.subscribe(TOPIC, 1);
      Serial.printf("완료, 구독 %s\n", TOPIC);
    } else {
      Serial.printf("실패 rc=%d, 2초 뒤 다시\n", mqtt.state());
      delay(2000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  setLed(false);

  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.print("\nIP: ");
  Serial.println(WiFi.localIP());

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(1024);   // 알림 한 건이 약 600바이트 (기본 256으로는 잘림)
  mqtt.setCallback(onMessage);
}

void loop() {
  if (!mqtt.connected()) connectMqtt();
  mqtt.loop();
}
