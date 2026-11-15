#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include "secrets.h"

#define PIN_SERVO  14   // D5
#define PIN_BUZZER 12   // D6

const int MIN_DEG = 20, MAX_DEG = 160;   // 왕복 범위
const int STEP_DEG = 2;                  // 한 번에 움직이는 각도
const unsigned long STEP_MS = 15;        // 움직이는 간격 (작을수록 빠름)
const unsigned long BEEP_MS = 150;       // 부저 삐- 간격 (0이면 계속 울림)

ESP8266WebServer server(80);
Servo motor;
bool danger = false, beepOn = false;
int deg = MIN_DEG, dir = 1;
unsigned long lastStep = 0, lastBeep = 0;

void setLed(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); }  // LOW가 켜짐

void setDanger(bool on) {
  if (on == danger) return;                    // 같은 상태가 다시 오면 무시
  danger = on;
  setLed(on);
  if (!on) { beepOn = false; digitalWrite(PIN_BUZZER, LOW); }
  Serial.println(on ? "DANGER: 모터 정지, 부저 ON" : "SAFE: 모터 재가동, 부저 OFF");
}

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
  setDanger(level == "danger" || level == "warn");   // 그 외(safe, unknown)는 안전 동작
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  setLed(false);
  motor.attach(PIN_SERVO, 500, 2400);        // SG90 펄스 범위
  motor.write(deg);

  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.print("\nIP: ");
  Serial.println(WiFi.localIP());

  server.on("/notify", HTTP_POST, handleNotify);
  server.begin();
}

void loop() {
  server.handleClient();

  if (Serial.available()) {                  // 시험용: 시리얼 모니터에서 d / s
    char c = Serial.read();
    if (c == 'd') setDanger(true);
    else if (c == 's') setDanger(false);
  }

  unsigned long now = millis();
  if (!danger) {                             // 안전: 계속 왕복
    if (now - lastStep >= STEP_MS) {
      lastStep = now;
      deg += dir * STEP_DEG;
      if (deg >= MAX_DEG || deg <= MIN_DEG) {
        deg = constrain(deg, MIN_DEG, MAX_DEG);
        dir = -dir;
      }
      motor.write(deg);
    }
  } else {                                   // 위험: 그 자리에서 멈추고 부저
    if (BEEP_MS == 0) digitalWrite(PIN_BUZZER, HIGH);
    else if (now - lastBeep >= BEEP_MS) {
      lastBeep = now;
      beepOn = !beepOn;
      digitalWrite(PIN_BUZZER, beepOn ? HIGH : LOW);
    }
  }
}
