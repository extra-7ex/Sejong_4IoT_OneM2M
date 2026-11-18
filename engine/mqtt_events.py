"""Experimental oneM2M MQTT event creation with response correlation."""
import json
import threading
import uuid
from urllib.parse import urlsplit


class UncertainWriteError(TimeoutError):
    """The CSE may have created the CIN despite an absent response."""


class MQTTEventWriter:
    def __init__(self, host, port, cse_id, cse_base, origin, events_path, timeout=5):
        if not cse_id or "/" in cse_id or not origin or "/" in origin:
            raise ValueError("provide CSE ID without slash and an originator")
        name = urlsplit(cse_base).path.strip("/")
        if not name or not events_path.startswith("/"):
            raise ValueError("CSEBase and events path required")
        self.host, self.port, self.cse_id, self.origin, self.timeout = host, port, cse_id, origin, timeout
        self.target = name + events_path
        self.request_topic = f"/oneM2M/req/{origin}/{cse_id}/json"
        self.response_topic = f"/oneM2M/resp/{origin}/{cse_id}/json"
        self.client = None
        self.ready = threading.Event()
        self.pending = {}
        self.lock = threading.Lock()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.subscribe(self.response_topic, qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if not any(code.is_failure for code in reason_codes):
            self.ready.set()

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.ready.clear()

    def on_message(self, client, userdata, message):
        try:
            response = json.loads(message.payload.decode("utf-8"))
            if not isinstance(response, dict):
                return
            rqi = response.get("rqi")
            with self.lock:
                pending = self.pending.get(rqi)
                if pending:
                    pending[1].append(response)
                    pending[0].set()
        except (ValueError, UnicodeDecodeError):
            return

    def start(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="risk-events-" + uuid.uuid4().hex[:12])
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()
        if not self.ready.wait(self.timeout):
            self.close()
            raise TimeoutError("MQTT event response subscription not ready")

    def create_event_cin(self, event):
        if not self.ready.is_set():
            raise ConnectionError("MQTT event response subscription unavailable")
        rqi = "risk-" + uuid.uuid4().hex
        request = {"op": 1, "to": self.target, "fr": self.origin, "rqi": rqi, "rvi": "3", "ty": 4,
                   "pc": {"m2m:cin": {"con": json.dumps(event, separators=(",", ":"))}}}
        waiter, responses = threading.Event(), []
        with self.lock:
            self.pending[rqi] = (waiter, responses)
        try:
            info = self.client.publish(self.request_topic, json.dumps(request, separators=(",", ":")), qos=1)
            if info.rc != 0:
                raise ConnectionError(f"MQTT publish rejected locally: {info.rc}")
            if not waiter.wait(self.timeout):
                raise UncertainWriteError(f"no oneM2M response for {rqi}; CIN creation may still have occurred")
            response = responses[0]
            if response.get("rsc") != 2001:
                raise RuntimeError(f"oneM2M event creation rejected: rsc={response.get('rsc')}")
            return {"rqi": rqi, "rsc": response["rsc"], "response": response}
        finally:
            with self.lock:
                self.pending.pop(rqi, None)

    def close(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
