"""Experimental tinyIoT MQTT notification input; SUB provisioning is external.

This adapter understands the direct m2m:sgn payload observed from the test CSE.
It does not claim that this payload is a fully interoperable oneM2M request or
that the server validates a verification response.
"""
import json
import logging
import queue
import time
import uuid

LOG = logging.getLogger("safezone-riskengine.mqtt")


class MQTTNotifications:
    def __init__(self, app, host, port, topic, max_age_s=3.0, queue_size=64, client_id=None):
        if not topic or "+" in topic or "#" in topic or max_age_s <= 0:
            raise ValueError("a specific MQTT topic and positive queue age are required")
        self.app, self.host, self.port, self.topic = app, host, port, topic
        self.max_age_s = max_age_s
        self.client_id = client_id or "risk-observe-" + uuid.uuid4().hex[:12]
        self.queue = queue.Queue(maxsize=queue_size)
        self.overflow = False
        self.client = None

    def _put(self, item):
        try:
            self.queue.put_nowait(item)
        except queue.Full:
            self.overflow = True

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._put(("fault", "mqtt_connection_refused", time.monotonic()))
        else:
            client.subscribe(self.topic, qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            self._put(("fault", "mqtt_subscription_refused", time.monotonic()))
        else:
            self._put(("info", "mqtt_subscription_ready", time.monotonic()))

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self._put(("fault", "mqtt_disconnected", time.monotonic()))

    def on_message(self, client, userdata, message):
        if message.retain:
            self._put(("fault", "mqtt_retained_notification_rejected", time.monotonic()))
            return
        self._put(("message", bytes(message.payload), time.monotonic()))

    def start(self):
        import paho.mqtt.client as mqtt
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=self.client_id)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect_async(self.host, self.port, keepalive=30)
        self.client.loop_start()

    def _fault(self, reason):
        LOG.warning("MQTT input: %s", reason)
        self.app.publish_transition(self.app.engine.mark_input_fault(reason))

    def process_next(self, timeout=0.1):
        if self.overflow:
            self.overflow = False
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
            self._fault("mqtt_notification_queue_overflow")
            return
        try:
            kind, value, received = self.queue.get(timeout=timeout)
        except queue.Empty:
            return
        if kind == "info":
            LOG.info("MQTT input: %s", value)
            return
        if kind == "fault":
            self._fault(value)
            return
        if time.monotonic() - received > self.max_age_s:
            self._fault("mqtt_notification_queue_stale")
            return
        try:
            message = json.loads(value.decode("utf-8"))
            sgn = message.get("m2m:sgn") if isinstance(message, dict) else None
            if not isinstance(sgn, dict):
                raise ValueError("expected direct m2m:sgn")
            if sgn.get("vrq") is True:
                LOG.info("MQTT verification notification received; response protocol not validated")
                return
            decision = self.app.accept_message(message, received_mono_s=received, dedupe=True)
            LOG.info("MQTT notification processed: %s (%s)", decision.get("status"), decision.get("reason"))
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            self._fault("mqtt_invalid_notification: " + str(exc))

    def close(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
