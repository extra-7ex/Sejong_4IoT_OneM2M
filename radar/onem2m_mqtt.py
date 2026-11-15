"""oneM2M MQTT 바인딩으로 CIN을 만드는 작은 클라이언트 (onem2m/mqtt.md 규격).

요청 토픽  /oneM2M/req/<originator>/<CSE_BASE_RI>/json   (publish)
응답 토픽  /oneM2M/resp/<originator>/<CSE_BASE_RI>/json  (subscribe)
메시지는 감싸지 않은 JSON {op, to, fr, rqi, rvi, ty, pc}이고 `to`는 앞에 `/` 없이 CSEBase 이름부터 쓴다.

필요: paho-mqtt (Pi: `sudo apt install python3-paho-mqtt`)
"""
import json
import threading
import time
import uuid

import paho.mqtt.client as mqtt


class OneM2MMqtt:
    def __init__(self, host, cse_name, cse_ri, origin, port=1883, client_id=None, qos=1, log=print):
        self.cse_name, self.cse_ri, self.origin, self.qos, self.log = cse_name, cse_ri, origin, qos, log
        self.req_topic = f'/oneM2M/req/{origin}/{cse_ri}/json'
        self.resp_topic = f'/oneM2M/resp/{origin}/{cse_ri}/json'
        self._pending = {}                 # rqi -> [보낸 시각, Event, 응답]
        self._lock = threading.Lock()
        self.sent = self.ok = self.failed = 0
        cid = client_id or f'{origin}-{uuid.uuid4().hex[:6]}'   # 장치마다 달라야 서로 끊지 않음
        try:                               # paho-mqtt 2.x
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid)
        except AttributeError:             # paho-mqtt 1.x
            self.client = mqtt.Client(client_id=cid)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(1, 10)
        self._ready = threading.Event()
        self.client.connect_async(host, port, keepalive=30)
        self.client.loop_start()
        if not self._ready.wait(5):        # 첫 요청이 연결 전에 나가 버리지 않게 잠깐 기다린다
            self.log(f'!! MQTT 브로커 {host}:{port}에 아직 연결되지 않음 (계속 다시 시도)')

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        client.subscribe(self.resp_topic, qos=self.qos)    # 다시 연결돼도 구독을 다시 건다
        self.log(f'MQTT 연결됨 (rc={rc}) → 요청 {self.req_topic}')
        self._ready.set()

    def _on_message(self, client, userdata, msg):
        try:
            resp = json.loads(msg.payload.decode('utf-8'))
        except ValueError:
            return
        with self._lock:
            p = self._pending.pop(resp.get('rqi'), None)
        if p is None:
            return
        rsc = resp.get('rsc')
        if rsc in (2000, 2001, '2000', '2001'):
            self.ok += 1
        else:
            self.failed += 1
            self.log(f'!! CSE 응답 rsc={rsc} rqi={resp.get("rqi")} {str(resp.get("pc"))[:120]}')
        p[2] = resp
        p[1].set()

    def connected(self):
        return self.client.is_connected()

    def create_cin(self, path, con, wait_s=0):
        """path는 CSEBase 아래 경로(예: 'AE-forklift01/radar'). con이 dict면 JSON 문자열로 바꿔 보낸다.
        wait_s > 0이면 응답을 그만큼 기다려 돌려준다(없으면 None). 0이면 보내기만 한다."""
        rqi = f'{self.origin}-{time.time_ns()}'
        msg = {'op': 1, 'to': f'{self.cse_name}/{path.strip("/")}', 'fr': self.origin, 'rqi': rqi,
               'rvi': '3', 'ty': 4, 'pc': {'m2m:cin': {'con': con if isinstance(con, str) else json.dumps(con)}}}
        ev = threading.Event()
        entry = [time.time(), ev, None]     # 응답이 오면 _on_message가 entry[2]에 넣는다
        with self._lock:
            self._pending[rqi] = entry
            for k in [k for k, v in self._pending.items() if time.time() - v[0] > 30]:
                del self._pending[k]       # 30초 넘게 응답이 없던 요청은 잊는다
        info = self.client.publish(self.req_topic, json.dumps(msg), qos=self.qos)
        self.sent += 1
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.failed += 1
            self.log(f'!! MQTT 보내기 실패 rc={info.rc} (브로커 연결 확인)')
            return None
        if wait_s > 0:
            ev.wait(wait_s)
            return entry[2]                 # 시간 안에 응답이 없으면 None
        return None

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()
