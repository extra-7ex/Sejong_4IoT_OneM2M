"""Isolated demo: MEC011 discovery followed by a mock Vision HTTP request.

Not RiskEngine, real Vision, safety control, or a oneM2M integration.
"""
import json
from urllib.request import urlopen

MEC_URL = "http://127.0.0.1:18080/safezone-a/mep-a/mec_service_mgmt/v1/services?ser_name=safezone-mock-vision"
EXPECTED_LOCAL_ENDPOINT = "http://127.0.0.1:18081/mock-vision"

with urlopen(MEC_URL, timeout=3) as response:
    services = json.load(response)
if len(services) != 1 or services[0].get("state") != "ACTIVE":
    raise RuntimeError("expected one ACTIVE mock Vision service")
endpoint = services[0]["transportInfo"]["endpoint"]["uris"][0]
if endpoint != EXPECTED_LOCAL_ENDPOINT:
    raise RuntimeError("unexpected endpoint; refusing to contact it")
with urlopen(endpoint, timeout=3) as response:
    data = json.load(response)
if data.get("source") != "mock" or data.get("zone") != "A" or not isinstance(data.get("tracks"), list):
    raise RuntimeError("unexpected mock Vision response")
print("PASS: MEC011 discovery -> local mock Vision response")
print(json.dumps(data, ensure_ascii=False))
