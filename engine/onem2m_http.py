"""Small oneM2M HTTP client for tinyIoT's HTTP binding."""

from __future__ import annotations

import json
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
        status, headers, body = self._request("GET", self.config["radar_path"])
        if not 200 <= status < 300:
            raise RuntimeError(f"radar GET failed: HTTP {status}: {body[:300]!r}")
        try:
            return json.loads(body.decode("utf-8")), body
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("radar GET did not return JSON") from exc

    def create_event_cin(self, event: dict) -> dict:
        # con is intentionally a JSON string, matching alert_node.ino which accepts
        # both string and object forms. This avoids depending on a tinyIoT coercion.
        body = json.dumps({"m2m:cin": {"con": json.dumps(event, separators=(",", ":"))}}).encode("utf-8")
        status, headers, response_body = self._request(
            "POST", self.config["events_path"], body, "application/json;ty=4",
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
