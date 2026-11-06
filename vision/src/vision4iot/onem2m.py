"""tinyIoT(oneM2M) HTTP 클라이언트 — 표준 라이브러리만 (CLAUDE.md 11장 요청 형식, 팀 스크립트와 같은 헤더).

    c = Client("http://127.0.0.1:3000", "TinyIoT", "Cforklift01")
    status, body = c.post_cin("AE-forklift01/radar", {"ts": ..., "targets": []})

HTTP 오류(4xx·5xx)는 (status, body)로 돌려주고, 연결 자체가 안 되면 OSError를 던진다.
"""
import itertools
import json
import time
import urllib.error
import urllib.request

TY_AE, TY_CNT, TY_CIN, TY_SUB = 2, 3, 4, 23
NET_CREATE_CHILD = 3        # 구독 알림 조건: 아래에 새 리소스(CIN)가 생기면


class Client:
    def __init__(self, base_url, cse_name, originator, timeout=2.0):
        if not base_url:
            raise ValueError("CSE 주소(base_url)가 비어 있음 — config.local.yaml의 onem2m.base_url 또는 --base-url")
        self.root = f"{base_url.rstrip('/')}/{cse_name.strip('/')}"
        self.originator = originator
        self.timeout = timeout
        self._n = itertools.count(1)

    def url(self, path=""):
        return self.root + (f"/{path.strip('/')}" if path else "")

    def request(self, method, path="", body=None, ty=None):
        headers = {"X-M2M-Origin": self.originator,
                   "X-M2M-RI": f"{self.originator}-{int(time.time() * 1000)}-{next(self._n)}",
                   "X-M2M-RVI": "3", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
            headers["Content-Type"] = f"application/json;ty={ty}"
        req = urllib.request.Request(self.url(path), data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, _json(r.read())
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())

    def get(self, path=""):
        return self.request("GET", path)

    def post_cin(self, cnt_path, con):
        """con이 dict·list면 JSON 문자열로 바꿔 보낸다 — tinyIoT는 객체 con을 400(invalid attribute : con)으로 거부한다.
        팀 엔진·ESP는 문자열 con을 JSON으로 풀어 읽는다."""
        if not isinstance(con, str):
            con = json.dumps(con, ensure_ascii=False, separators=(",", ":"))
        return self.request("POST", cnt_path, {"m2m:cin": {"con": con}}, TY_CIN)

    def create_ae(self, rn, api):
        """409(이미 있음)도 성공으로 본다."""
        return self.request("POST", "", {"m2m:ae": {"rn": rn, "api": api, "rr": True, "srv": ["3"]}}, TY_AE)

    def create_cnt(self, parent, rn, mni):
        return self.request("POST", parent, {"m2m:cnt": {"rn": rn, "mni": mni}}, TY_CNT)

    def create_sub(self, parent, rn, nu):
        """parent 아래 새 CIN마다 nu(URL)로 알림 (팀 sub_alert_node.sh와 같은 nct 1, net 3)."""
        body = {"m2m:sub": {"rn": rn, "nu": [nu], "nct": 1, "enc": {"net": [NET_CREATE_CHILD]}}}
        return self.request("POST", parent, body, TY_SUB)

    def delete(self, path):
        return self.request("DELETE", path)


def cin_con(notification):
    """구독 알림(m2m:sgn) 또는 CIN 응답에서 con을 꺼내 dict로. con이 JSON 문자열이면 푼다. 없으면 None."""
    msg = notification.get("m2m:sgn", notification) if isinstance(notification, dict) else {}
    rep = (msg.get("nev") or {}).get("rep") or msg
    cin = rep.get("m2m:cin") if isinstance(rep, dict) else None
    if not isinstance(cin, dict) or "con" not in cin:
        return None
    con = cin["con"]
    if isinstance(con, str):
        try:
            return json.loads(con)
        except ValueError:
            return {"raw": con}
    return con


def _json(raw):
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return raw.decode(errors="replace")
