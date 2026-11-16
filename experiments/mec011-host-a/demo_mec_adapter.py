"""One-shot MEC adapter demo for the loopback SafeZone trial services.

Use 'init' to provision a trial AE and two containers, 'request' to post
one request CIN, and 'run' to read that request and post its result.
Use a fresh AE name for each independent demo. CAdmin is for this test CSE.
"""

import argparse
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


CSE = "http://127.0.0.1:13000/TinyIoT"
MEC = "http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1"
SERVICE = "safezone-mock-vision"
VISION = "http://127.0.0.1:18081/mock-vision"
OPERATION = "get_latest_vision"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def exchange(url, *, body=None, resource_type=None, origin="CAdmin"):
    headers = {"Accept": "application/json"}
    if resource_type is not None or url.startswith(CSE + "/"):
        headers.update({
            "X-M2M-Origin": origin,
            "X-M2M-RI": uuid4().hex,
            "X-M2M-RVI": "3",
        })
    if resource_type is not None:
        headers["Content-Type"] = f"application/json;ty={resource_type}"
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, headers=headers)
    with build_opener(NoRedirect()).open(request, timeout=5) as response:
        return response.status, response.headers.get("X-M2M-RSC"), response.read()


def create(url, resource_type, body, origin="CAdmin"):
    status, rsc, _ = exchange(url, body=body, resource_type=resource_type, origin=origin)
    if (status, rsc) != (201, "2001"):
        raise ValueError(f"oneM2M create returned HTTP {status}, rsc={rsc}")


def init(ae, ae_url):
    create(CSE, 2, {"m2m:ae": {"rn": ae, "api": "Nmecadapter", "rr": True, "srv": ["3"]}},
           origin=f"C{uuid4().hex[:12]}")
    for name in ("requests", "results"):
        create(ae_url, 3, {"m2m:cnt": {"rn": name, "mni": 20}})


def result_for(request_id):
    result = {
        "request_id": request_id,
        "service_name": SERVICE,
        "registry_state": None,
        "call_status": "discovery_failed",
        "http_status": None,
        "frame_ts": None,
        "cam_ok": None,
        "freshness": "unknown",
    }
    try:
        query = urlencode({"ser_name": SERVICE})
        _, _, data = exchange(f"{MEC}/services?{query}")
        entries = json.loads(data)
        if not isinstance(entries, list) or len(entries) != 1:
            raise ValueError("expected one registered Vision service")
        entry = entries[0]
        if entry["serName"] != SERVICE:
            raise ValueError("unexpected service name")
        result["registry_state"] = entry["state"]
        if entry["state"] != "ACTIVE":
            raise ValueError("Vision service is not ACTIVE")
        endpoint = entry["transportInfo"]["endpoint"]["uris"][0]
        if endpoint != VISION:
            raise ValueError("unexpected endpoint for the loopback demo")
    except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        result["reason"] = str(exc)
        return result

    result["call_status"] = "call_failed"
    try:
        status, _, data = exchange(endpoint)
        result["http_status"] = status
        vision = json.loads(data)
        if vision.get("source") != "mock" or not isinstance(vision.get("tracks"), list):
            raise ValueError("unexpected mock Vision response")
        result["track_count"] = len(vision["tracks"])
        result["call_status"] = "ok"
    except HTTPError as exc:
        result["http_status"] = exc.code
        result["reason"] = str(exc)
    except (URLError, OSError, AttributeError, ValueError) as exc:
        result["reason"] = str(exc)
    return result


def read_cin(url):
    status, rsc, raw = exchange(url)
    if (status, rsc) != (200, "2000"):
        raise ValueError(f"oneM2M retrieve returned HTTP {status}, rsc={rsc}")
    content = json.loads(raw)["m2m:cin"]["con"]
    return json.loads(content) if isinstance(content, str) else content


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", value):
        raise argparse.ArgumentTypeError("expected 1–48 ASCII letters, digits, underscores or hyphens")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ae", required=True, type=identifier)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    for command in ("request", "run"):
        commands.add_parser(command).add_argument("request_id", type=identifier)
    args = parser.parse_args()
    ae_url = f"{CSE}/{args.ae}"
    requests = f"{ae_url}/requests"
    results = f"{ae_url}/results"

    if args.command == "init":
        init(args.ae, ae_url)
        print(f"Trial resources ready: {ae_url}")
        return
    request = {"request_id": args.request_id, "operation": OPERATION}
    if args.command == "request":
        create(requests, 4, {"m2m:cin": {"rn": f"req-{args.request_id}", "con": json.dumps(request)}})
        print(f"Request CIN created: {requests}/req-{args.request_id}")
        return

    request_cin = read_cin(f"{requests}/req-{args.request_id}")
    if request_cin != request:
        raise SystemExit("request CIN does not match the expected request ID and operation")
    name = f"res-{args.request_id}"
    result_url = f"{results}/{name}"
    try:
        result = read_cin(result_url)
    except HTTPError as exc:
        if exc.code != 404:
            raise
        result = result_for(args.request_id)
        create(results, 4, {"m2m:cin": {"rn": name, "con": json.dumps(result)}})
        result = read_cin(result_url)
    print(f"Result CIN: {result_url}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
