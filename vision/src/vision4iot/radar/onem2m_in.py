"""레이더 입력: tinyIoT `AE-forklift01/radar/la`를 뒤에서 계속 읽는다 (CLAUDE.md 9장 `onem2m`).

- 팀 radar con(mm, cm/s, con은 객체 또는 JSON 문자열)을 우리 Target(m, m/s)으로 바꾼다(base.from_team_con).
- 새 CIN(ri가 바뀜)이 stale_s(1초) 넘게 없으면 radar_ok=False, 표적 없음 → 융합은 카메라만으로(camera_only).
  엔진과 같은 기준이다. 오래된 la를 새 값으로 착각하지 않게, 처음 읽은 la는 다음 새 CIN이 올 때까지 쓰지 않는다.
- 읽는 주체는 originator `CVisionAI` → radar에 VisionAI 읽기 권한(ACP)이 있어야 한다(없으면 403, 2장 빈 연결 5).
"""
import threading
import time

from vision4iot.onem2m import Client
from vision4iot.radar.base import from_team_con


class OneM2MRadar:
    def __init__(self, client, path, hz=10.0, stale_s=1.0, flip_x=False, flip_v=False, clock=time.monotonic):
        self.client, self.path = client, path.rstrip("/") + "/la"
        self.period, self.stale_s = 1.0 / hz, stale_s
        self.flip = (flip_x, flip_v)
        self.clock = clock
        self._lock = threading.Lock()
        self._targets, self._ri, self._t_new, self._first = [], None, None, True
        self.last_error = None
        self._stop = threading.Event()
        self._th = None

    @classmethod
    def from_cfg(cls, cfg, base_url=None):
        o, r = cfg["onem2m"], cfg["radar"]
        client = Client(base_url or o.get("base_url"), o["cse_name"], o["originator"], timeout=1.0)
        return cls(client, o["radar_path"], flip_x=r.get("flip_x", False), flip_v=r.get("flip_v", False))

    def poll_once(self):
        """la를 한 번 읽어 반영. 시험에서도 직접 부른다."""
        try:
            status, body = self.client.get(self.path)
        except OSError as e:
            self.last_error = f"CSE 연결 안 됨: {e}"
            return
        if status != 200 or not isinstance(body, dict) or "m2m:cin" not in body:
            self.last_error = f"HTTP {status}" + (" — VisionAI 읽기 권한(ACP) 필요" if status == 403 else "")
            return
        cin = body["m2m:cin"]
        ri = cin.get("ri")
        if ri == self._ri:
            return
        try:
            _, targets = from_team_con(cin.get("con"), *self.flip)
        except (ValueError, KeyError, TypeError) as e:
            self.last_error = f"radar con 형식 오류: {e}"
            return
        first = self._first
        with self._lock:
            self._ri, self._first = ri, False
            if not first:                      # 시작할 때 이미 있던 la는 오래된 값일 수 있어 쓰지 않는다
                self._targets, self._t_new = targets, self.clock()
        self.last_error = None

    def get(self):
        """(targets, radar_ok). 1초 넘게 새 CIN이 없으면 ([], False)."""
        with self._lock:
            if self._t_new is None or self.clock() - self._t_new > self.stale_s:
                return [], False
            return list(self._targets), True

    def _run(self):
        while not self._stop.is_set():
            t0 = time.monotonic()
            self.poll_once()
            self._stop.wait(max(0.0, self.period - (time.monotonic() - t0)))

    def start(self):
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        return self

    def stop(self):
        self._stop.set()
