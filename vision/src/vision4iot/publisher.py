"""fusedTracks 내보내기 (CLAUDE.md 10장·11장): stdout | jsonl | onem2m.

onem2m: 시작할 때 `AE-VisionAI`(api NVisionAI)와 `fusedTracks` CNT(mni 100)를 만든다(이미 있으면 409 → 그대로 씀,
팀 setup_onem2m.sh는 안 만든다). 그다음 프레임마다 CIN 1건(con = JSON 문자열). 보내기는 뒤 스레드에서 하고,
밀리면 가장 최신 것만 보낸다(영상 처리를 막지 않는다).
"""
import json
import queue
import sys
import threading
import time
from pathlib import Path

from vision4iot.onem2m import Client


class StdoutPublisher:
    """1초에 한 번 최신 메시지를 한 줄로."""

    def __init__(self, every_s=1.0):
        self.every_s, self._last = every_s, 0.0

    def publish(self, msg):
        now = time.monotonic()
        if now - self._last >= self.every_s:
            self._last = now
            print("fusedTracks " + json.dumps(msg, ensure_ascii=False), flush=True)

    def close(self):
        pass


class JsonlPublisher:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(self.path, "a", encoding="utf-8")

    def publish(self, msg):
        self.f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def close(self):
        self.f.close()


class OneM2MPublisher:
    def __init__(self, client, fused_path, mni=100, log=print):
        self.client, self.path, self.log = client, fused_path.strip("/"), log
        self.sent = self.failed = 0
        self.last_error = None
        self._q = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._ensure(mni)
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def _ensure(self, mni):
        ae, cnt = self.path.split("/", 1)
        s1, _ = self.client.create_ae(ae, "N" + ae.removeprefix("AE-"))
        s2, _ = self.client.create_cnt(ae, cnt, mni)
        if s1 not in (201, 409) or s2 not in (201, 409):
            raise RuntimeError(f"{ae}/{cnt} 만들기 실패: AE HTTP {s1}, CNT HTTP {s2}")
        self.log(f"fusedTracks → {self.client.url(self.path)} (AE {s1}, CNT {s2}; 409 = 이미 있음)")

    def publish(self, msg):
        try:
            self._q.put_nowait(msg)
        except queue.Full:                      # 밀리면 오래된 것을 버리고 최신만
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
            self._q.put_nowait(msg)

    def _run(self):
        while not self._stop.is_set():
            try:
                msg = self._q.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                status, body = self.client.post_cin(self.path, msg)
                ok = status in (200, 201)
                self.last_error = None if ok else f"HTTP {status} {str(body)[:120]}"
            except OSError as e:
                ok, self.last_error = False, f"CSE 연결 안 됨: {e}"
            self.sent += ok
            self.failed += not ok

    def close(self):
        self._stop.set()
        self._th.join(timeout=1.0)


def make_publisher(cfg, mode=None, base_url=None):
    mode = mode or cfg["output"]["mode"]
    if mode == "stdout":
        return StdoutPublisher()
    if mode == "jsonl":
        from vision4iot.config import resolve
        return JsonlPublisher(resolve(cfg["output"]["jsonl_file"]))
    if mode == "onem2m":
        o = cfg["onem2m"]
        client = Client(base_url or o.get("base_url"), o["cse_name"], o["originator"], timeout=1.0)
        return OneM2MPublisher(client, o["fused_path"], log=lambda s: print(s, file=sys.stderr, flush=True))
    raise ValueError(f"output.mode {mode!r}: stdout | jsonl | onem2m")
