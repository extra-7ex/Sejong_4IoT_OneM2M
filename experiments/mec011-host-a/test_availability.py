"""Test MEC011 manual availability notifications; isolated local mock only."""
import json
import subprocess
import time
import uuid
from urllib.request import Request, urlopen

BASE = "http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1"
APP = "safezone-vision-test"
NAME = "safezone-mock-vision"
CONTAINER = "safezone-mec-experiment-notify-test-1"


def request(url, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=5) as response:
        body = response.read()
        return response.status, json.loads(body) if body else None


def main():
    _, services = request(BASE + "/services?ser_name=" + NAME)
    if len(services) != 1:
        raise RuntimeError("expected exactly one mock service; run setup_mock_app.py first")
    service = services[0]
    self_url = service["_links"]["self"]["href"]
    if not self_url.startswith("http://localhost:18080/safezone-a/mep-a/"):
        raise RuntimeError("unexpected service URL")
    marker = "safezone-test-" + uuid.uuid4().hex
    subscription = {"subscriptionType": "SerAvailabilityNotificationSubscription",
                    "callbackReference": "http://notify-test/notify?test=" + marker,
                    "filteringCriteria": {"serNames": [NAME]}}
    status, sub = request(BASE + f"/applications/{APP}/subscriptions", "POST", subscription)
    if status != 201:
        raise RuntimeError("subscription creation failed")
    sub_url = sub["_links"]["self"]["href"]
    if not sub_url.startswith("http://localhost:18080/safezone-a/mep-a/"):
        raise RuntimeError("unexpected subscription URL")
    try:
        for state in ("INACTIVE", "ACTIVE"):
            service["state"] = state
            status, _ = request(self_url, "PUT", service)
            if status != 200:
                raise RuntimeError("service update failed")
            for attempt in range(30):
                log = subprocess.run(["docker", "logs", "--tail", "100", CONTAINER],
                                     capture_output=True, text=True, check=True).stdout
                if any(marker in line and ('state\\x22:\\x22' + state) in line for line in log.splitlines()):
                    print("PASS: state", state, "notification received")
                    break
                if attempt == 29:
                    raise RuntimeError("notification not observed for " + state)
                time.sleep(0.1)
    finally:
        service["state"] = "ACTIVE"
        request(self_url, "PUT", service)
        request(sub_url, "DELETE")


if __name__ == "__main__":
    main()
