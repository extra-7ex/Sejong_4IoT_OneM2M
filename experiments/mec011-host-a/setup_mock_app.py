"""Provision a test app and register a synthetic local Vision service.

This simulates the absent orchestration layer via the isolated Redis app store.
Never use this script with production resources.
"""
import json
import subprocess
import time
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18080/safezone-a/mep-a"
APP = "safezone-vision-test"
NAME = "safezone-mock-vision"


def request(path, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = Request(BASE + path, data=body, method=method,
                  headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        content = response.read()
        return response.status, json.loads(content) if content else None


def main():
    subprocess.run(["docker", "compose", "-p", "safezone-mec-experiment", "exec", "-T", "redis", "redis-cli", "HSET",
                    "data:sbox:safezone-a:apps:" + APP, "id", APP, "name", "MockVision",
                    "node", "mep-a", "type", "USER", "persist", "true"], check=True)
    subprocess.run(["docker", "compose", "-p", "safezone-mec-experiment", "restart", "mep"], check=True)
    for attempt in range(30):
        try:
            code, _ = request(f"/mec_app_support/v1/applications/{APP}/confirm_ready", "POST", {"indication": "READY"})
            break
        except (OSError, TimeoutError):
            if attempt == 29:
                raise
            time.sleep(1)
    if code != 204:
        raise RuntimeError(f"unexpected ready response {code}")
    _, entries = request(f"/mec_service_mgmt/v1/services?ser_name={NAME}")
    if entries:
        raise RuntimeError("test service already registered: inspect it instead of creating duplicates")
    payload = {"serName": NAME, "version": "1.0", "state": "ACTIVE", "serializer": "JSON",
               "transportInfo": {"id": "mock-http", "name": "http", "type": "REST_HTTP",
                                 "protocol": "HTTP", "version": "1.1",
                                 "endpoint": {"uris": ["http://127.0.0.1:18081/mock-vision"]}}}
    code, registered = request(f"/mec_service_mgmt/v1/applications/{APP}/services", "POST", payload)
    if code != 201:
        raise RuntimeError(f"unexpected registration response {code}")
    print(f"READY 204; REGISTER {code}; service id={registered['serInstanceId']}")


if __name__ == "__main__":
    main()
