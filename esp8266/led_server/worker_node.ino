// 작업자 경보 노드 (ESP8266): 켜지면 tinyIoT에 스스로 등록하고, 자기 alert에 위험이 기록되면 부저를 울림
#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include "secrets.h"                                   // WIFI_SSID, WIFI_PASS, CSE_HOST

// ===== 설정 =====
#ifndef CSE_HOST
#error "Define CSE_HOST in secrets.h, for example http://<PI_IP>:3000"
#endif
const String CSE_NAME = "TinyIoT-MN";
const String NODE     = "worker01";                     // 작업자 노드를 더 만들면 worker02, worker03 ...
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

int m2m(const char* method, const String& path, int ty, const String& body, String* response = nullptr) {
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
  if (response) *response = http.getString();
  Serial.printf("%-6s %-28s -> %d\n", method, path.length() ? path.c_str() : "/", code);
  http.end();
  return code;
}
bool ok(int c) { return c == 200 || c == 201; }
bool createdOrExists(int c) { return ok(c) || c == 409; } // 리소스 생성 POST에만 사용
String js(JsonDocument& d) { String s; serializeJson(d, s); return s; }

bool retrieve(const String& path, const char* key, JsonDocument& d) {
  String body;
  if (m2m("GET", path, 0, "", &body) != 200 || deserializeJson(d, body) || !d[key].is<JsonObject>()) {
    Serial.println("!! 기존 리소스 확인 실패: " + path);
    return false;
  }
  Serial.println("유지: " + path + " ri=" + d[key]["ri"].as<String>());
  return true;
}

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

  // 1) AE: 알림 받을 주소(poa)에 포트 :80을 꼭 넣음
  JsonObject ae = d["m2m:ae"].to<JsonObject>();
  ae["rn"] = AE;
  ae["api"] = "Nworker-alarm";
  ae["rr"] = true;
  ae["srv"].add("3");
  ae["lbl"].add("type:worker-alarm");                   // MEC 경보 서비스가 이 라벨로 노드를 찾음
  ae["poa"].add("http://" + myIp + ":80/notify");
  int aeCode = m2m("POST", "", 2, js(d));
  if (!createdOrExists(aeCode)) return false;
  if (aeCode == 409) {                                  // 이미 등록됨: 네트워크가 바뀌었을 수 있으니 poa를 지금 IP로 고침
    d.clear();
    d["m2m:ae"]["poa"].add("http://" + myIp + ":80/notify");
    if (m2m("PUT", "/" + AE, 0, js(d)) != 200) {
      Serial.println("!! poa 갱신 실패: 등록을 재시도함");
      return false;
    }
  }
  if (!retrieve("/" + AE, "m2m:ae", d)) return false;
  if (d["m2m:ae"]["aei"].as<String>() != ORIGIN ||
      d["m2m:ae"]["poa"].size() != 1 ||
      d["m2m:ae"]["poa"][0].as<String>() != "http://" + myIp + ":80/notify") {
    Serial.println("!! AE-ID 또는 poa 불일치: 등록 실패");
    return false;
  }

  // 2) 신규 ACP: 엔진 CREATE만, 운영자 기존 35, 소유자/pvs 기존 63 유지.
  // alert/status는 아직 이 ACP를 공유하므로 리소스별 최소 권한은 아님.
  d.clear();
  JsonObject acp = d["m2m:acp"].to<JsonObject>();
  acp["rn"] = "acp-" + NODE;
  JsonArray acr = acp["pv"]["acr"].to<JsonArray>();
  JsonObject own = acr.add<JsonObject>();
  own["acor"].add(ORIGIN); own["acop"] = 63;
  JsonObject engine = acr.add<JsonObject>();
  engine["acor"].add("Criskengine"); engine["acop"] = 1;
  JsonObject admin = acr.add<JsonObject>();
  admin["acor"].add("CAdmin"); admin["acop"] = 35;
  JsonObject self = acp["pvs"]["acr"].to<JsonArray>().add<JsonObject>();
  self["acor"].add(ORIGIN); self["acop"] = 63;
  int acpCode = m2m("POST", "/" + AE, 1, js(d));
  if (!createdOrExists(acpCode)) return false;           // ACP 없이 CNT를 만들지 않음
  if (!retrieve("/" + AE + "/acp-" + NODE, "m2m:acp", d)) return false;
  Serial.println(acpCode == 409 ? "기존 ACP 재사용 (정책 변경 없음):" : "신규 ACP 정책:");
  serializeJson(d["m2m:acp"]["pv"], Serial); Serial.println();
  serializeJson(d["m2m:acp"]["pvs"], Serial); Serial.println();

  // 3) 컨테이너: alert(위험 알림 받는 곳), status(살아 있음 신호)
  const char* cnts[] = {"alert", "status"};
  for (const char* cn : cnts) {
    d.clear();
    JsonObject cnt = d["m2m:cnt"].to<JsonObject>();
    cnt["rn"] = cn;
    cnt["mni"] = 20;                                    // 최근 20개만 보관
    cnt["acpi"].add(CSE_NAME + "/" + AE + "/acp-" + NODE);
    if (!createdOrExists(m2m("POST", "/" + AE, 3, js(d)))) return false;
    if (!retrieve("/" + AE + "/" + cn, "m2m:cnt", d)) return false;
    Serial.print("현재 CNT acpi (변경 없음): ");
    serializeJson(d["m2m:cnt"]["acpi"], Serial); Serial.println();
  }

  // 4) 구독: 알림 대상을 '나 자신(AE-ID)'으로 → 확인 요청 없이 만들어지고, 알림은 poa로 옴
  d.clear();
  JsonObject sub = d["m2m:sub"].to<JsonObject>();
  sub["rn"] = "sub-" + NODE;
  sub["nu"].add(ORIGIN);
  sub["nct"] = 1;
  sub["enc"]["net"].add(3);
  if (!createdOrExists(m2m("POST", "/" + AE + "/alert", 23, js(d)))) return false;
  if (!retrieve("/" + AE + "/alert/sub-" + NODE, "m2m:sub", d)) return false;
  JsonVariant existingSub = d["m2m:sub"];
  bool notifySelf = false, notifyCreate = false;
  for (JsonVariant nu : existingSub["nu"].as<JsonArray>()) {
    if (nu.as<String>() == ORIGIN) notifySelf = true;
  }
  for (JsonVariant net : existingSub["enc"]["net"].as<JsonArray>()) {
    if (net.as<int>() == 3) notifyCreate = true;
  }
  if (!notifySelf || !notifyCreate || existingSub["nct"].as<int>() != 1) {
    Serial.println("!! 기존 SUB 설정 불일치: 삭제/변경 없이 등록 중단");
    return false;
  }

  if (!sendStatus("online")) return false;
  Serial.println("경보 그룹 가입은 별도 운영 작업 (자동 추가하지 않음)");
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
