"""Experimental long-running adapter for isolated local oneM2M requests."""
import argparse
import json
import logging
import queue
import signal
import time
from urllib.error import HTTPError
from uuid import uuid4

import demo_mec_adapter as demo


LOG = logging.getLogger("mec-adapter")
MAX_PENDING = 128


def parse_request(cin):
    name = cin.get("rn", "")
    if not isinstance(name, str) or not name.startswith("req-"):
        raise ValueError("unexpected request resource name")
    request_id = demo.identifier(name[4:])
    raw = cin.get("con")
    request = json.loads(raw) if isinstance(raw, str) else raw
    if request != {"request_id": request_id, "operation": demo.OPERATION}:
        raise ValueError("invalid request body")
    return request_id


def process(ae_url, request_id):
    requests = f"{ae_url}/requests"
    results = f"{ae_url}/results"
    expected = {"request_id": request_id, "operation": demo.OPERATION}
    if demo.read_cin(f"{requests}/req-{request_id}") != expected:
        raise ValueError("request has changed")
    result_url = f"{results}/res-{request_id}"
    try:
        return demo.read_cin(result_url)
    except HTTPError as exc:
        if exc.code != 404:
            raise
    result = demo.result_for(request_id)
    try:
        demo.create(results, 4, {"m2m:cin": {"rn": f"res-{request_id}", "con": json.dumps(result)}})
    except HTTPError as exc:
        if exc.code != 409:
            raise
    return demo.read_cin(result_url)


def scan(requests):
    status, rsc, raw = demo.exchange(requests + "?rcn=4")
    if status != 200 or rsc != "2000":
        raise ValueError("request container lookup failed")
    container = json.loads(raw)["m2m:cnt"]
    entries = container.get("m2m:cin", [])
    if isinstance(entries, dict):
        entries = [entries]
    for cin in entries:
        try:
            yield parse_request(cin)
        except (ValueError, TypeError, KeyError) as exc:
            LOG.warning("Ignoring invalid request: %s", exc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ae", required=True, type=demo.identifier)
    parser.add_argument("--pi-mn", action="store_true")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--scan-interval", type=float, default=5)
    args = parser.parse_args()
    if not args.topic or "+" in args.topic or "#" in args.topic or args.scan_interval <= 0:
        parser.error("a specific topic and positive scan interval are required")
    if args.pi_mn:
        demo.CSE = "http://127.0.0.1:3000/TinyIoT-MN"
    ae_url = f"{demo.CSE}/{args.ae}"
    requests = f"{ae_url}/requests"

    import paho.mqtt.client as mqtt
    pending = queue.Queue(maxsize=MAX_PENDING)
    stop = False

    def connected(client, userdata, flags, reason, properties):
        if reason.is_failure:
            LOG.error("MQTT connection refused: %s", reason)
        else:
            client.subscribe(args.topic, qos=1)

    def subscribed(client, userdata, mid, reason_codes, properties):
        if any(code.is_failure for code in reason_codes):
            LOG.error("MQTT subscription rejected")
        else:
            LOG.info("MQTT subscription ready; request scan will reconcile")

    def disconnected(client, userdata, flags, reason, properties):
        LOG.warning("MQTT disconnected: %s", reason)

    def message(client, userdata, packet):
        if packet.retain:
            LOG.warning("Retained notification ignored")
            return
        try:
            signal_body = json.loads(packet.payload)["m2m:sgn"]
            if signal_body.get("vrq") is True:
                LOG.info("CSE verification received; standard response not implemented")
                return
            cin = signal_body["nev"]["rep"]["m2m:cin"]
            pending.put_nowait(parse_request(cin))
        except (ValueError, TypeError, KeyError, AttributeError, queue.Full) as exc:
            LOG.warning("Notification ignored; scan will reconcile: %s", exc)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                         client_id="mec-adapter-" + uuid4().hex[:12])
    client.on_connect, client.on_subscribe = connected, subscribed
    client.on_disconnect, client.on_message = disconnected, message
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def shutdown(signum, frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    client.connect_async("127.0.0.1", 1883, keepalive=30)
    client.loop_start()
    next_scan = 0
    try:
        while not stop:
            if time.monotonic() >= next_scan:
                try:
                    for request_id in scan(requests):
                        try:
                            pending.put_nowait(request_id)
                        except queue.Full:
                            break
                except Exception:
                    LOG.exception("Request scan failed")
                next_scan = time.monotonic() + args.scan_interval
            try:
                request_id = pending.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                result = process(ae_url, request_id)
                LOG.info("request_id=%s call_status=%s", request_id, result.get("call_status"))
            except Exception:
                LOG.exception("Request processing failed: %s", request_id)
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
