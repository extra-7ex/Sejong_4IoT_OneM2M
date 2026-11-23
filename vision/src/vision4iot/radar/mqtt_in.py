"""Receive tinyIoT radar CIN notifications through a configured MQTT topic."""
import json
import math
import threading
import time
import uuid

from vision4iot.onem2m import cin_con
from vision4iot.radar.base import from_team_con


class MQTTRadar:
    def __init__(self, host, port, topic, stale_s=1.0, flip_x=False, flip_v=False,
                 clock=time.monotonic):
        if not topic or "+" in topic or "#" in topic or stale_s <= 0:
            raise ValueError("a specific topic and positive stale interval are required")
        self.host, self.port, self.topic = host, port, topic
        self.stale_s, self.flip, self.clock = stale_s, (flip_x, flip_v), clock
        self._lock = threading.Lock()
        self._targets, self._ri, self._received = [], None, None
        self.client = None
        self.last_error = "waiting for MQTT connection"

    def invalidate(self, reason):
        with self._lock:
            self._targets, self._received = [], None
            self.last_error = reason

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self.invalidate("MQTT connection rejected")
        else:
            client.subscribe(self.topic, qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            self.invalidate("MQTT subscription rejected")
        else:
            self.last_error = None

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.invalidate("MQTT disconnected")

    def on_message(self, client, userdata, message):
        if message.retain:
            self.invalidate("retained notification rejected")
            return
        try:
            body = json.loads(message.payload.decode("utf-8"))
            signal = body["m2m:sgn"]
            if not isinstance(signal, dict):
                raise ValueError("invalid notification")
            if signal.get("vrq") is True:
                return
            cin = signal["nev"]["rep"]["m2m:cin"]
            ri = cin["ri"]
            if not isinstance(ri, str) or not ri:
                raise ValueError("missing CIN ri")
            con = cin_con(body)
            if not isinstance(con, dict) or not isinstance(con.get("targets"), list):
                raise ValueError("radar targets must be a list")
            if len(con["targets"]) > 3:
                raise ValueError("too many radar targets")
            for target in con["targets"]:
                if not isinstance(target, dict):
                    raise ValueError("invalid radar target")
                for field in ("x", "y", "v"):
                    value = target.get(field, 0 if field == "v" else None)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        raise ValueError("invalid radar coordinate or speed")
            _, targets = from_team_con(con, *self.flip)
            with self._lock:
                if ri == self._ri:
                    return
                self._ri, self._targets, self._received = ri, targets, self.clock()
                self.last_error = None
        except (ValueError, TypeError, KeyError, AttributeError, UnicodeDecodeError) as exc:
            self.invalidate("invalid MQTT notification: " + str(exc))

    def get(self):
        with self._lock:
            if self._received is None or self.clock() - self._received > self.stale_s:
                return [], False
            return list(self._targets), True

    def start(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                  client_id="vision-radar-" + uuid.uuid4().hex[:12])
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()
        return self

    def stop(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
