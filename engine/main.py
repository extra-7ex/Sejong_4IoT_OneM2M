"""SafeZone RiskEngine service. Standard-library only."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import time
from typing import Any

from .config import RiskConfig, one_m2m_config
from .onem2m_http import OneM2MHTTP
from .risk_engine import InputError, RiskEngine, normalize_radar_cin


LOG = logging.getLogger("safezone-riskengine")


class RiskApplication:
    """Shared pipeline used by both polling and oneM2M notification transports."""
    def __init__(self, cse: OneM2MHTTP, engine: RiskEngine):
        self.cse = cse
        self.engine = engine
        self.last_cin_ri: str | None = None
        self.last_published_status: str | None = None

    def accept_message(self, message: Any, received_mono_s: float | None = None,
                       dedupe: bool = False) -> dict:
        try:
            frame = normalize_radar_cin(message)
        except InputError as exc:
            decision = self.engine.mark_input_fault(str(exc))
            self.publish_transition(decision)
            return decision
        if dedupe and not frame.cin_ri:
            decision = self.engine.mark_input_fault("CIN has no ri; cannot safely deduplicate or detect stale polling")
            self.publish_transition(decision)
            return decision
        if dedupe and frame.cin_ri and frame.cin_ri == self.last_cin_ri:
            return self.engine.snapshot(received_mono_s)
        if frame.cin_ri:
            self.last_cin_ri = frame.cin_ri
        decision = self.engine.process_frame(frame, received_mono_s)
        self.publish_transition(decision)
        return decision

    def poll_once(self) -> dict:
        try:
            message, _ = self.cse.get_latest_radar_cin()
            decision = self.accept_message(message, dedupe=True)
        except Exception as exc:
            LOG.warning("radar polling error: %s", exc)
            decision = self.engine.mark_input_fault(f"radar_poll_error: {exc}")
            self.publish_transition(decision)
        return decision

    def tick(self) -> dict:
        decision = self.engine.snapshot()
        self.publish_transition(decision)
        return decision

    def publish_transition(self, decision: dict) -> None:
        status = decision.get("status", "UNKNOWN")
        if status == self.last_published_status:
            return
        LOG.info("risk status: %s (%s)", status, decision.get("reason"))
        try:
            result = self.cse.create_event_cin(decision)
            LOG.info("events CIN POST response: %s", json.dumps(result, ensure_ascii=False))
            self.last_published_status = status
        except Exception:
            # Keep the last published state unchanged; a later transition/retry can report it.
            LOG.exception("could not register risk event CIN")


def _notification_server(app: RiskApplication, host: str, port: int) -> HTTPServer:
    class NotificationHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - stdlib callback name
            if self.path != "/notify":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            try:
                message = json.loads(raw.decode("utf-8"))
                sgn = message.get("m2m:sgn", {}) if isinstance(message, dict) else {}
                if isinstance(sgn, dict) and sgn.get("vrq") is True:
                    # oneM2M subscription verification request: acknowledge without evaluating.
                    self.send_response(200)
                    self.send_header("X-M2M-RSC", "2000")
                    self.end_headers()
                    return
                decision = app.accept_message(message, dedupe=True)
                LOG.info("notification processed: %s", json.dumps(decision, ensure_ascii=False))
                self.send_response(200)
                self.send_header("X-M2M-RSC", "2000")
                self.end_headers()
            except Exception as exc:
                LOG.exception("notification processing failed")
                decision = app.engine.mark_input_fault(f"notification_error: {exc}")
                app.publish_transition(decision)
                self.send_response(200)  # acknowledge delivery; state is UNKNOWN and logged
                self.send_header("X-M2M-RSC", "2000")
                self.end_headers()

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.info("notification HTTP: " + fmt, *args)

    return HTTPServer((host, port), NotificationHandler)


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeZone 2D distance/CPA RiskEngine")
    parser.add_argument("--transport", choices=("polling", "notification"), default="polling")
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cse_config = one_m2m_config()
    app = RiskApplication(OneM2MHTTP(cse_config), RiskEngine(RiskConfig.from_env()))
    LOG.info("transport=%s cse=%s radar_path=%s events_path=%s", args.transport,
             cse_config["cse_base"], cse_config["radar_path"], cse_config["events_path"])

    if args.transport == "notification":
        server = _notification_server(app, args.listen, args.port)
        server.timeout = min(float(cse_config["poll_interval_s"]), 0.5)
        LOG.info("listening for oneM2M notifications at http://%s:%d/notify", args.listen, args.port)
        try:
            while True:
                server.handle_request()
                app.tick()  # notification silence must also age into UNKNOWN
        except KeyboardInterrupt:
            LOG.info("notification server stopping")
        finally:
            server.server_close()
        return

    interval = float(cse_config["poll_interval_s"])
    while True:
        app.poll_once()
        app.tick()  # also turns a silent/stale stream into UNKNOWN
        time.sleep(interval)


if __name__ == "__main__":
    main()
