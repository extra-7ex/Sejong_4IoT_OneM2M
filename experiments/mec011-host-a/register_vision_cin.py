"""Register the demo Vision CIN endpoint in the local AdvantEDGE registry.

This initializes one demo app in the experiment Redis store if it is absent.
It emulates app provisioning; it is not a MEC orchestrator. An existing
service with a different endpoint is never overwritten.
"""

import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
APP = "safezone-vision-cin-app"
NAME = "safezone-vision-cin-trial"


def request(url, method="GET", payload=None):
    raw = None if payload is None else json.dumps(payload).encode()
    req = Request(url, data=raw, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        body = response.read()
        return response.status, json.loads(body) if body else None


def docker(project, *args):
    return subprocess.run(["docker", "compose", "-p", project, *args], cwd=HERE,
                          check=True, text=True, capture_output=True).stdout.strip()


def wait_for_registry(service_api):
    for attempt in range(30):
        try:
            return request(service_api + "/services?ser_name=" + quote(NAME))[1]
        except urllib.error.HTTPError as exc:
            if exc.code not in (502, 503, 504) or attempt == 29:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 29:
                raise
        time.sleep(1)


def provision(project, base, endpoint):
    service_api = base + "/mec_service_mgmt/v1"
    services = wait_for_registry(service_api)
    if not isinstance(services, list) or len(services) > 1:
        raise RuntimeError("unexpected or duplicate registry entries; nothing was changed")
    if services:
        current = services[0].get("transportInfo", {}).get("endpoint", {}).get("uris", [])
        if current != [endpoint] or services[0].get("state") != "ACTIVE":
            raise RuntimeError("existing service has different endpoint or state; it was not changed")
        print("Vision service already registered with expected endpoint")
        return

    key = "data:sbox:safezone-a:apps:" + APP
    exists = docker(project, "exec", "-T", "redis", "redis-cli", "EXISTS", key)
    if exists == "0":
        docker(project, "exec", "-T", "redis", "redis-cli", "HSET", key,
               "id", APP, "name", "SafeZoneVision", "node", "mep-a", "type", "USER", "persist", "true")
    elif exists == "1":
        values = docker(project, "exec", "-T", "redis", "redis-cli", "HMGET", key,
                        "id", "name", "node", "type").splitlines()
        if values != [APP, "SafeZoneVision", "mep-a", "USER"]:
            raise RuntimeError("existing demo app metadata differs; it was not changed")
    else:
        raise RuntimeError(f"unexpected Redis EXISTS response: {exists}")

    # AdvantEDGE loads the app store at startup, including after a partial setup.
    # This is initial provisioning and causes a brief registry interruption.
    docker(project, "restart", "mep")
    for attempt in range(30):
        try:
            status, _ = request(base + f"/mec_app_support/v1/applications/{APP}/confirm_ready",
                                "POST", {"indication": "READY"})
            if status == 204:
                break
            raise RuntimeError(f"unexpected confirm_ready response: {status}")
        except (OSError, urllib.error.URLError):
            if attempt == 29:
                raise
            time.sleep(1)
    payload = {"serName": NAME, "version": "1.0", "state": "ACTIVE", "serializer": "JSON",
               "transportInfo": {"id": "cse-http", "name": "http", "type": "REST_HTTP",
                                 "protocol": "HTTP", "version": "1.1",
                                 "endpoint": {"uris": [endpoint]}}}
    status, _ = request(service_api + f"/applications/{APP}/services", "POST", payload)
    if status != 201:
        raise RuntimeError(f"unexpected registration response: {status}")
    print("Vision CIN service registered; IPE can discover and read the endpoint")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project", default="safezone-mec-experiment")
    ap.add_argument("--mec-base", default="http://127.0.0.1:18080/safezone-a/mep-a")
    ap.add_argument("--cse-base", default="http://127.0.0.1:3000/TinyIoT-MN")
    args = ap.parse_args()
    for url in (args.mec_base, args.cse_base):
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or parsed.hostname not in ("127.0.0.1", "localhost"):
            ap.error("the demo registry and CSE must be local HTTP(S) addresses")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            ap.error("URLs must not contain credentials, queries or fragments")
    provision(args.project, args.mec_base.rstrip("/"),
              args.cse_base.rstrip("/") + "/AE-VisionAI/fusedTracks/la")


if __name__ == "__main__":
    main()
