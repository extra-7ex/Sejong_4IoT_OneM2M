"""Create the resources for the SafeZone demo without deleting existing resources.

Run against a newly installed CSE, after the worker has registered itself.
Existing resources are checked, never silently modified. In particular, an
existing ACP or alarm group that differs from this profile stops the setup.
"""

import argparse
import sys
from urllib.parse import urlsplit

from onem2m.mn_to_in_bridge import Cse


class SetupError(RuntimeError):
    pass


def valid_base(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.path.strip("/"):
        raise argparse.ArgumentTypeError("expected an HTTP(S) URL ending in the CSEBase name")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("credentials, query strings and fragments are not accepted")
    return value.rstrip("/")


def get(cse, path, key):
    status, body = cse.request("GET", path)
    if status == 404:
        return None
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get(key), dict):
        raise SetupError(f"GET {path or '/'}: HTTP {status}: {body}")
    return body[key]


def create(cse, parent, key, value, ty):
    status, body = cse.request("POST", parent, ty, {key: value})
    if status != 201:
        raise SetupError(f"POST {parent or '/'} ({value.get('rn')}): HTTP {status}: {body}")
    print(f"created {parent}/{value.get('rn')}")


def ensure_ae(admin, base, name, origin, api):
    path = "/" + name
    ae = get(admin, path, "m2m:ae")
    if ae is None:
        create(Cse(base, origin, "3", 5), "", "m2m:ae",
               {"rn": name, "api": api, "rr": True, "srv": ["3"]}, 2)
        ae = get(admin, path, "m2m:ae")
    if ae is None or ae.get("aei") != origin:
        raise SetupError(f"{path}: AE-ID is not {origin}")


def ensure_policy(admin, base_name, parent, name, rules):
    path = f"{parent}/{name}"
    expected = [{"acor": [origin], "acop": mask} for origin, mask in rules]
    acp = get(admin, path, "m2m:acp")
    if acp is None:
        create(admin, parent, "m2m:acp", {
            "rn": name, "pv": {"acr": expected},
            "pvs": {"acr": [{"acor": ["CAdmin"], "acop": 63}]},
        }, 1)
        acp = get(admin, path, "m2m:acp")
    have = acp.get("pv", {}).get("acr", [])
    actual = {(origin, rule.get("acop")) for rule in have for origin in rule.get("acor", [])}
    if actual != set(rules):
        raise SetupError(f"{path}: policy does not match the demo rules; policy left unchanged")
    pvs = acp.get("pvs", {}).get("acr", [])
    actual_pvs = {(origin, rule.get("acop")) for rule in pvs for origin in rule.get("acor", [])}
    if actual_pvs != {("CAdmin", 63)}:
        raise SetupError(f"{path}: unexpected ACP administration rights; policy left unchanged")
    return f"{base_name}{path}"


def ensure_cnt(admin, base_name, parent, name, owner, readers=(), creators=(), mni=100,
               policy_parent=None):
    # A CNT owner retains its rights when an explicit acpi replaces inherited access.
    rules = [(owner, 63), ("CAdmin", 63)]
    rules += [(origin, 2) for origin in readers if origin not in (owner, "CAdmin")]
    rules += [(origin, 1) for origin in creators if origin not in (owner, "CAdmin")]
    policy = ensure_policy(admin, base_name, policy_parent or parent, "acp-demo-" + name, rules)
    path = f"{parent}/{name}"
    cnt = get(admin, path, "m2m:cnt")
    if cnt is None:
        create(admin, parent, "m2m:cnt", {"rn": name, "mni": mni, "acpi": [policy]}, 3)
        cnt = get(admin, path, "m2m:cnt")
    if not cnt or policy not in (cnt.get("acpi") or []):
        raise SetupError(f"{path}: expected ACP is not linked; existing CNT left unchanged")
    return cnt


def ensure_branch(admin, parent, name):
    path = f"{parent}/{name}"
    if get(admin, path, "m2m:cnt") is None:
        create(admin, parent, "m2m:cnt", {"rn": name}, 3)
    return path


def has_create(admin, base_name, cnt, origin):
    for ref in cnt.get("acpi") or []:
        path = "/" + ref.removeprefix(base_name + "/").lstrip("/")
        acp = get(admin, path, "m2m:acp")
        if acp and any(origin in rule.get("acor", []) and rule.get("acop", 0) & 1
                       for rule in acp.get("pv", {}).get("acr", [])):
            return True
    return False


def provision_mn(base, dashboard_origin):
    admin = Cse(base, "CAdmin", "3", 5)
    base_name = urlsplit(base).path.rstrip("/").split("/")[-1]
    get(admin, "", "m2m:cb")
    for name, origin, api in [
        ("AE-forklift01", "Cforklift01", "Nforklift"),
        ("AE-zonealarm01", "Czonealarm01", "Nzonealarm"),
        ("AE-riskengine", "Criskengine", "Nriskengine"),
        ("AE-VisionAI", "CVisionAI", "Nvision"),
        ("AE-mecIPE", "CmecIPE", "NmecIPE"),
        ("AE-bridge", "Cbridge", "Nbridge"),
    ]:
        ensure_ae(admin, base, name, origin, api)
    ensure_cnt(admin, base_name, "/AE-forklift01", "radar", "Cforklift01",
               readers=("Criskengine", "CVisionAI", "Cbridge", dashboard_origin))
    forklift = ensure_cnt(admin, base_name, "/AE-forklift01", "alert", "Cforklift01",
                          readers=(dashboard_origin,), creators=("Criskengine",), mni=20)
    zone = ensure_cnt(admin, base_name, "/AE-zonealarm01", "alert", "Czonealarm01",
                      creators=("Criskengine",), mni=20)
    ensure_cnt(admin, base_name, "/AE-riskengine", "events", "Criskengine",
               readers=("Cbridge", dashboard_origin))
    ensure_cnt(admin, base_name, "/AE-VisionAI", "fusedTracks", "CVisionAI",
               readers=("Criskengine", "CmecIPE", dashboard_origin))
    services = ensure_branch(admin, "/AE-mecIPE", "MecServices")
    service = ensure_branch(admin, services, "safezone-vision")
    ensure_cnt(admin, base_name, service, "status", "CmecIPE", readers=(dashboard_origin,),
               policy_parent="/AE-mecIPE")

    worker_ae = get(admin, "/AE-worker01", "m2m:ae")
    worker = get(admin, "/AE-worker01/alert", "m2m:cnt")
    status = get(admin, "/AE-worker01/status", "m2m:cnt")
    sub = get(admin, "/AE-worker01/alert/sub-worker01", "m2m:sub") if worker else None
    if (not worker_ae or worker_ae.get("aei") != "Cworker01" or not worker_ae.get("poa")
            or not worker or not status or not sub or "Cworker01" not in (sub.get("nu") or [])
            or sub.get("nct") != 1 or 3 not in (sub.get("enc", {}).get("net") or [])):
        raise SetupError("worker AE, poa, alert/status or alert subscription is incomplete: "
                         "start the worker and let it finish registration, then rerun")
    if not has_create(admin, base_name, worker, "Criskengine"):
        raise SetupError("worker alert ACP does not grant Criskengine CREATE; existing ACP left unchanged")

    group_policy = ensure_policy(admin, base_name, "", "acp-demo-alarm-group",
                                 [("CAdmin", 63), ("Criskengine", 1)])
    paths = [f"{base_name}/AE-forklift01/alert", f"{base_name}/AE-worker01/alert",
             f"{base_name}/AE-zonealarm01/alert"]
    group = get(admin, "/grp-safezone-alarms", "m2m:grp")
    if group is None:
        create(admin, "", "m2m:grp", {"rn": "grp-safezone-alarms", "mt": 3, "mnm": 20,
                "csy": 1, "mid": paths, "macp": [group_policy]}, 9)
        group = get(admin, "/grp-safezone-alarms", "m2m:grp")
    expected = {forklift.get("ri"), worker.get("ri"), zone.get("ri")}
    if set(group.get("mid") or []) != expected or group_policy not in (group.get("macp") or []):
        raise SetupError("existing alarm group membership or macp differs; group left unchanged")
    print("MN resources and group checked")


def provision_in(base):
    admin = Cse(base, "CAdmin", "3", 5)
    base_name = urlsplit(base).path.rstrip("/").split("/")[-1]
    get(admin, "", "m2m:cb")
    ensure_ae(admin, base, "AE-dashboard-in", "Cdashboard", "Ndashboard")
    ensure_ae(admin, base, "AE-safezone", "Csafezone", "Nsafezone")
    ensure_cnt(admin, base_name, "/AE-safezone", "events", "Csafezone",
               readers=("Cdashboard",), mni=5000)
    print("IN history and dashboard resources checked")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mn", type=valid_base, default="http://127.0.0.1:3000/TinyIoT-MN")
    parser.add_argument("--in-base", type=valid_base, required=True)
    parser.add_argument("--in-cse-id", default="id-in")
    args = parser.parse_args(argv)
    if not args.in_cse_id or "/" in args.in_cse_id:
        parser.error("--in-cse-id must be the CSE ID without slashes")
    try:
        inn = Cse(args.in_base, "CAdmin", "3", 5)
        in_cb = get(inn, "", "m2m:cb")
        if not in_cb or in_cb.get("csi") != "/" + args.in_cse_id:
            raise SetupError("IN CSE-ID differs from --in-cse-id; nothing was provisioned")
        provision_mn(args.mn, f"/{args.in_cse_id}/Cdashboard")
        provision_in(args.in_base)
    except (SetupError, OSError, ValueError) as exc:
        print(f"Setup stopped: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
