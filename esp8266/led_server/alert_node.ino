#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ArduinoJson.h>
#include <Servo.h>
#include "secrets.h"

#define PIN_SERVO  14   // D5
#define PIN_BUZZER 12   // D6

const int CENTER = 0;   // 포크가 수평일 때 각도
const int SWING  = 30;   // 위아래 흔들 폭 (±20°, 30 넘기지 말 것)
const int MIN_DEG = CENTER - SWING, MAX_DEG = CENTER + SWING;
const int STEP_DEG = 2;                  // 한 번에 움직이는 각도
const unsigned long STEP_MS = 15;        // 움직이는 간격 (작을수록 빠름)
const unsigned long WARN_BEEP_MS   = 450;  // warn: 느린 경보 (포크는 계속 움직임)
const unsigned long DANGER_BEEP_MS = 150;  // danger: 빠른 경보 + 포크 정지
const unsigned long UNKNOWN_BEEP_MS = 1000; // unknown: 긴 경보 + 포크 정지 (센서·판단이 끊김)

ESP8266WebServer server(80);
Servo motor;
int mode = 0;                            // 0 safe, 1 warn, 2 danger, 3 unknown
bool beepOn = false;
int deg = MIN_DEG, dir = 1;
unsigned long lastStep = 0, lastBeep = 0;

void setLed(bool on) { digitalWrite(LED_BUILTIN, on ? LOW : HIGH); }  // LOW가 켜짐

void setMode(int m) {
  if (m == mode) return;                       // 같은 상태가 다시 오면 무시
  mode = m;
  setLed(m > 0);
  beepOn = false; lastBeep = 0;
  digitalWrite(PIN_BUZZER, LOW);
  const char* names[] = {"SAFE: 포크 동작, 부저 OFF", "WARN: 포크 동작, 느린 경보", "DANGER: 포크 정지, 빠른 경보",
                         "UNKNOWN: 포크 정지, 긴 경보 (센서·판단 끊김)"};
  Serial.println(names[m]);
}

// alert level → mode. 모르는 값(unknown, 빈 값 포함)은 알 수 없음으로 보고 멈춘다.
int levelToMode(const String& level) {
  if (level == "safe") return 0;
  if (level == "warn") return 1;
  if (level == "danger") return 2;
  return 3;
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
  setMode(levelToMode(level));               // unknown이면 danger처럼 포크를 멈춘다
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

  if (Serial.available()) {                  // 시험용: 시리얼 모니터에서 d / w / s / u
    char c = Serial.read();
    if (c == 'd') setMode(2);
    else if (c == 'w') setMode(1);
    else if (c == 's') setMode(0);
    else if (c == 'u') setMode(3);
  }

  unsigned long now = millis();
  if (mode < 2 && now - lastStep >= STEP_MS) {   // safe·warn만 포크 왕복 (danger·unknown은 정지)
    lastStep = now;
    deg += dir * STEP_DEG;
    if (deg >= MAX_DEG || deg <= MIN_DEG) {
      deg = constrain(deg, MIN_DEG, MAX_DEG);
      dir = -dir;
    }
    motor.write(deg);
  }
  unsigned long beepMs = mode == 3 ? UNKNOWN_BEEP_MS : mode == 2 ? DANGER_BEEP_MS : WARN_BEEP_MS;
  if (mode > 0 && now - lastBeep >= beepMs) {  // warn·danger·unknown: 부저
    lastBeep = now;
    beepOn = !beepOn;
    digitalWrite(PIN_BUZZER, beepOn ? HIGH : LOW);
  }
}
