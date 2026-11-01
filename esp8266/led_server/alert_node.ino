#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ArduinoJson.h>
#include "secrets.h"

ESP8266WebServer server(80);

void setLed(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); }  // LOW가 켜짐

// tinyIoT 알림 수신 (구독 확인 요청 + alert 새 데이터)
void handleNotify() {
  String body = server.arg("plain");
  Serial.println("수신: " + body);
  server.sendHeader("X-M2M-RSC", "2000");   // oneM2M 성공 응답
  server.send(200);

  JsonDocument doc;
  if (deserializeJson(doc, body)) return;
  JsonVariant sgn = doc["m2m:sgn"];
  if (sgn["vrq"] | false) return;            // 구독 확인 요청이면 응답만 하고 끝
  JsonVariant cin = sgn["nev"]["rep"]["m2m:cin"];
  if (cin.isNull()) return;                  // 새 데이터 알림이 아니면 무시

  JsonVariant con = cin["con"];
  String level;
  if (con.is<const char*>()) {               // con이 문자열로 온 경우
    JsonDocument c;
    deserializeJson(c, con.as<const char*>());
    level = c["level"] | "";
  } else {
    level = con["level"] | "";
  }
  Serial.println("level = " + level);
  setLed(level == "danger" || level == "warn");
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

  server.on("/notify", HTTP_POST, handleNotify);
  server.begin();
}

void loop() { server.handleClient(); }
