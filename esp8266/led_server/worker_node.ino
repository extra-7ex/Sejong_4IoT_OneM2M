// 작업자 경보 노드 (ESP8266): 켜지면 tinyIoT에 스스로 등록하고, 자기 alert에 위험이 기록되면 부저를 울림
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"                                   // WIFI_SSID, WIFI_PASS

// ===== 설정 =====
#ifndef CSE_HOST                                        // secrets.h에서 바꾼다 (핫스팟 등 네트워크가 바뀌면 Pi의 새 IP)
#define CSE_HOST "http://192.168.219.103:3000"
#endif
const String CSE_NAME = "TinyIoT-MN";
const String NODE     = "worker01";                     // 작업자 노드를 더 만들면 worker02, worker03 ...
const String WRITERS[] = {"Criskengine", "CAdmin"};     // 이 노드의 alert에 기록할 수 있는 쪽
#define PIN_BUZZER 12                                   // D6
const unsigned long HEARTBEAT_MS = 30000;               // 살아 있음 신호 주기
const unsigned long WARN_MS = 500, DANGER_MS = 120;     // 부저 간격

const String AE = "AE-" + NODE;
const String ORIGIN = "C" + NODE;

ESP8266WebServer server(80);
String myIp;
bool registered = false, beepOn = false;
int mode = 0, beatFail = 0;                             // mode: 0 조용, 1 warn, 2 danger
unsigned long lastBeat = 0, lastTry = 0, lastBeep = 0;

int m2m(const char* method, const String& path, int ty, const String& body) {
  WiFiClient wc;
  HTTPClient http;
  http.setTimeout(3000);
  http.begin(wc, String(CSE_HOST) + "/" + CSE_NAME + path);
  http.addHeader("X-M2M-Origin", ORIGIN);
  http.addHeader("X-M2M-RI", "r" + String(millis()));
  http.addHeader("X-M2M-RVI", "3");
  http.addHeader("Accept", "application/json");
  http.addHeader("Content-Type", ty ? "application/json;ty=" + String(ty) : String("application/json"));
  int code = http.sendRequest(method, body);
  Serial.printf("%-6s %-28s -> %d\n", method, path.length() ? path.c_str() : "/", code);
  http.end();
  return code;
}
bool ok(int c) { return c == 200 || c == 201 || c == 409; }   // 409 = 이미 있음
String js(JsonDocument& d) { String s; serializeJson(d, s); return s; }

bool sendStatus(const char* state) {
  JsonDocument c;
  c["state"] = state; c["ip"] = myIp; c["rssi"] = WiFi.RSSI(); c["mode"] = mode;
  JsonDocument d;
  d["m2m:cin"]["con"] = js(c);                          // tinyIoT는 con에 문자열만 받음
  return ok(m2m("POST", "/" + AE + "/status", 4, js(d)));
}

bool registerNode() {
  myIp = WiFi.localIP().toString();
  Serial.println("== 등록 시작: " + AE + " (" + myIp + ")");
  JsonDocument d;

  m2m("DELETE", "/" + AE, 0, "");                       // 예전 등록을 지우고 새로 만듦 → 켤 때마다 '새 노드'로 나타남

  // 1) AE: 알림 받을 주소(poa)에 포트 :80을 꼭 넣음
  JsonObject ae = d["m2m:ae"].to<JsonObject>();
  ae["rn"] = AE;
  ae["api"] = "Nworker-alarm";
  ae["rr"] = true;
  ae["srv"].add("3");
  ae["lbl"].add("type:worker-alarm");                   // MEC 경보 서비스가 이 라벨로 노드를 찾음
  ae["poa"].add("http://" + myIp + ":80/notify");
  if (!ok(m2m("POST", "", 2, js(d)))) return false;

  // 2) 접근 권한: 엔진도 이 노드의 alert에 쓸 수 있게
  d.clear();
  JsonObject acp = d["m2m:acp"].to<JsonObject>();
  acp["rn"] = "acp-" + NODE;
  JsonArray acr = acp["pv"]["acr"].to<JsonArray>();
  JsonObject own = acr.add<JsonObject>();
  own["acor"].add(ORIGIN); own["acop"] = 63;
  JsonObject w = acr.add<JsonObject>();
  for (const String& s : WRITERS) w["acor"].add(s);
  w["acop"] = 35;                                       // 생성 + 조회 + 탐색
  JsonObject self = acp["pvs"]["acr"].to<JsonArray>().add<JsonObject>();
  self["acor"].add(ORIGIN); self["acop"] = 63;
  bool acpOk = ok(m2m("POST", "/" + AE, 1, js(d)));
  if (!acpOk) Serial.println("!! ACP 생성 실패: 엔진이 alert에 못 쓸 수 있음");

  // 3) 컨테이너: alert(위험 알림 받는 곳), status(살아 있음 신호)
  const char* cnts[] = {"alert", "status"};
  for (const char* cn : cnts) {
    d.clear();
    JsonObject cnt = d["m2m:cnt"].to<JsonObject>();
    cnt["rn"] = cn;
    cnt["mni"] = 20;                                    // 최근 20개만 보관
    if (acpOk) cnt["acpi"].add(CSE_NAME + "/" + AE + "/acp-" + NODE);
    if (!ok(m2m("POST", "/" + AE, 3, js(d)))) return false;
  }

  // 4) 구독: 알림 대상을 '나 자신(AE-ID)'으로 → 확인 요청 없이 만들어지고, 알림은 poa로 옴
  d.clear();
  JsonObject sub = d["m2m:sub"].to<JsonObject>();
  sub["rn"] = "sub-" + NODE;
  sub["nu"].add(ORIGIN);
  sub["nct"] = 1;
  sub["enc"]["net"].add(3);
  if (!ok(m2m("POST", "/" + AE + "/alert", 23, js(d)))) return false;

  sendStatus("online");
  Serial.println("== 등록 완료");
  return true;
}

void setMode(int m) {
  if (m == mode) return;
  mode = m;
  beepOn = false; lastBeep = 0;
  digitalWrite(PIN_BUZZER, LOW); digitalWrite(LED_BUILTIN, HIGH);
  const char* names[] = {"SAFE: 조용", "WARN: 느린 경보", "DANGER: 빠른 경보"};
  Serial.println(names[m]);
}

void handleNotify() {
  String body = server.arg("plain");
  server.sendHeader("X-M2M-RSC", "2000");
  server.send(200);
  Serial.println("수신: " + body);

  JsonDocument doc;
  if (deserializeJson(doc, body)) return;
  JsonVariant cin = doc["m2m:sgn"]["nev"]["rep"]["m2m:cin"];
  if (cin.isNull()) return;
  JsonVariant con = cin["con"];
  String level;
  if (con.is<const char*>()) { JsonDocument c; deserializeJson(c, con.as<const char*>()); level = c["level"] | ""; }
  else level = con["level"] | "";
  Serial.println("level = " + level);
  setMode(level == "danger" ? 2 : level == "warn" ? 1 : 0);
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT); digitalWrite(PIN_BUZZER, LOW);
  pinMode(LED_BUILTIN, OUTPUT); digitalWrite(LED_BUILTIN, HIGH);
  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nIP: " + WiFi.localIP().toString());
  server.on("/notify", HTTP_POST, handleNotify);
  server.begin();
  registered = registerNode();
  lastTry = lastBeat = millis();
}

void loop() {
  server.handleClient();
  unsigned long now = millis();

  // 등록에 실패했거나 IP가 바뀌면 10초 뒤 다시 등록
  if (WiFi.status() == WL_CONNECTED && (!registered || WiFi.localIP().toString() != myIp) && now - lastTry > 10000) {
    lastTry = now;
    registered = registerNode();
  }
  // 살아 있음 신호 (3번 연속 실패하면 다시 등록)
  if (registered && now - lastBeat > HEARTBEAT_MS) {
    lastBeat = now;
    if (sendStatus("online")) beatFail = 0;
    else if (++beatFail >= 3) { registered = false; beatFail = 0; }
  }
  // 시험용: 시리얼 모니터에서 d(위험) / w(경고) / s(안전) / r(다시 등록)
  if (Serial.available()) {
    char c = Serial.read();
    if (c == 'd') setMode(2); else if (c == 'w') setMode(1); else if (c == 's') setMode(0);
    else if (c == 'r') registered = registerNode();
  }
  // 부저 + LED
  if (mode > 0 && now - lastBeep >= (mode == 2 ? DANGER_MS : WARN_MS)) {
    lastBeep = now;
    beepOn = !beepOn;
    digitalWrite(PIN_BUZZER, beepOn ? HIGH : LOW);
    digitalWrite(LED_BUILTIN, beepOn ? LOW : HIGH);
  }
}
