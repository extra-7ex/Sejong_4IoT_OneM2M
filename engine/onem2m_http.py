"""Small oneM2M HTTP client for tinyIoT's HTTP binding."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid


class OneM2MHTTP:
    def __init__(self, config: dict[str, str]):
        self.config = config
        self.timeout = float(config["http_timeout_s"])

    def _request(self, method: str, path: str, body: bytes | None = None,
                 content_type: str | None = None) -> tuple[int, dict[str, str], bytes]:
        headers = {
            "X-M2M-Origin": self.config["origin"],
            "X-M2M-RI": "risk-" + uuid.uuid4().hex,
            "X-M2M-RVI": self.config["rvi"],
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(
            self.config["cse_base"] + path, data=body, headers=headers, method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status, dict(response.headers.items()), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers.items()), exc.read()

    def get_latest_radar_cin(self) -> tuple[dict, bytes]:
        return self.get_latest_cin(self.config["radar_path"])

    def get_latest_cin(self, path: str) -> tuple[dict, bytes]:
        status, headers, body = self._request("GET", path)
        if not 200 <= status < 300:
            raise RuntimeError(f"CIN GET failed for {path}: HTTP {status}: {body[:300]!r}")
        try:
            return json.loads(body.decode("utf-8")), body
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"CIN GET for {path} did not return JSON") from exc

    def create_event_cin(self, event: dict) -> dict:
        return self.create_cin(self.config["events_path"], event)

    def create_cin(self, path: str, event: dict) -> dict:
        # con is intentionally a JSON string, matching alert_node.ino which accepts
        # both string and object forms. This avoids depending on a tinyIoT coercion.
        body = json.dumps({"m2m:cin": {"con": json.dumps(event, separators=(",", ":"))}}).encode("utf-8")
        status, headers, response_body = self._request(
            "POST", path, body, "application/json;ty=4",
        )
        rsc = headers.get("X-M2M-RSC") or headers.get("x-m2m-rsc")
        if not 200 <= status < 300:
            raise RuntimeError(f"event CIN POST failed: HTTP {status}: {response_body[:300]!r}")
        if rsc is not None and rsc not in ("2000", "2001"):
            raise RuntimeError(f"event CIN rejected by oneM2M: X-M2M-RSC={rsc}, body={response_body[:300]!r}")
        try:
            response = json.loads(response_body.decode("utf-8")) if response_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = {"raw_response": response_body[:300].decode("utf-8", errors="replace")}
        return {"http_status": status, "x_m2m_rsc": rsc, "response": response}


class HTTPAlertWriter:
    """Writes the engine's alert to an existing alert container over HTTP (e.g. /AE-forklift01/alert).

    The forklift and worker nodes are subscribed to that container, so this is the real stop
    path. Only one writer may own it: turn off the radar node's local decision
    (RADAR_LOCAL_DECISION=0) before enabling this.
    """

    def __init__(self, http: OneM2MHTTP, path: str):
        self.http, self.path = http, path

    def create_event_cin(self, alert: dict) -> dict:
        result = self.http.create_cin(self.path, alert)
        check_fanout(result)
        return result


def check_fanout(result: dict) -> None:
    """A path ending in /fopt is a oneM2M group fan-out (onem2m/alarm_group.py): the CSE answers 2000 with
    one m2m:rsp per member container. Raise only when no member stored the alert, so one switched-off
    zone light cannot block the forklift stop; partial failures are logged."""
    agr = (result.get("response") or {}).get("m2m:agr") if isinstance(result, dict) else None
    if not isinstance(agr, dict):
        return
    rsps = agr.get("m2m:rsp") or []
    ok = [r for r in rsps if str(r.get("rsc")) in ("2000", "2001")]
    failed = [f"{r.get('to')}={r.get('rsc')}" for r in rsps if r not in ok]
    if not ok:
        raise RuntimeError(f"group fan-out reached no member: {failed or 'no members'}")
    if failed:
        logging.getLogger(__name__).warning("group fan-out: %d/%d members failed: %s",
                                            len(failed), len(rsps), ", ".join(failed))
