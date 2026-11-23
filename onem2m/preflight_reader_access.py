"""Read-only check of the demo IPE and bridge Origins against a running MN."""

import argparse
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

CHECKS = {
    "ipe": [("CmecIPE", "/AE-VisionAI/fusedTracks/la")],
    "bridge": [("Cbridge", "/AE-forklift01/radar/la"),
               ("Cbridge", "/AE-riskengine/events/la")],
}


def check(base: str, origin: str, path: str, timeout: float) -> int:
    headers = {"X-M2M-Origin": origin, "X-M2M-RI": uuid.uuid4().hex,
               "X-M2M-RVI": "3", "Accept": "application/json"}
    request = urllib.request.Request(base + path, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cse", default="http://127.0.0.1:3000/TinyIoT-MN")
    parser.add_argument("--role", choices=("ipe", "bridge", "all"), default="all")
    parser.add_argument("--timeout", type=float, default=5)
    args = parser.parse_args(argv)
    parsed = urllib.parse.urlsplit(args.cse)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
        parser.error("--cse must be an HTTP(S) CSE URL without embedded credentials")
    roles = CHECKS if args.role == "all" else (args.role,)
    passed = True
    for role in roles:
        for origin, path in CHECKS[role]:
            try:
                status = check(args.cse.rstrip("/"), origin, path, args.timeout)
                good = status == 200
                print(f"{role}: {origin} GET {path}: HTTP {status}")
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                good = False
                print(f"{role}: {origin} GET {path}: {type(exc).__name__}")
            passed = passed and good
    if not passed:
        print("Preflight failed; check AE, ACP, CSE and CIN availability before starting services.", file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
