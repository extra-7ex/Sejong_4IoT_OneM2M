#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>

const char* ssid = "와이파이이름";   // ← 변경
const char* pass = "와이파이비밀번호";       // ← 변경
ESP8266WebServer server(80);

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);  // 꺼진 상태로 시작

  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.begin(ssid, pass);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.print("\nIP: ");
  Serial.println(WiFi.localIP());

  server.on("/on",  []() { digitalWrite(LED_BUILTIN, LOW);  server.send(200, "text/plain", "ON"); });
  server.on("/off", []() { digitalWrite(LED_BUILTIN, HIGH); server.send(200, "text/plain", "OFF"); });
  server.begin();
}

void loop() { server.handleClient(); }
