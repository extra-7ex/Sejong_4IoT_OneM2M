"""radar_node.py의 끊김 처리 시험. 실제 LD2450 대신 가짜 시리얼을 쓴다.

    python3 -m unittest radar.test_radar_node     (저장소 루트에서)
"""

import contextlib
import io
import os
import re
import runpy
import sys
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("radar_node.py")


def frame(x_mm=None, y_mm=None):
    """LD2450 30바이트 프레임. 표적 하나(x, y) 또는 빈 프레임."""
    def enc(v):
        return (abs(v) | (0x8000 if v >= 0 else 0)).to_bytes(2, "little")
    slots = bytearray(24)
    if x_mm is not None:
        slots[0:8] = enc(x_mm) + enc(y_mm) + enc(0) + (0).to_bytes(2, "little")
    return b"\xAA\xFF\x03\x00" + bytes(slots) + b"\x55\xCC"


class Done(Exception):
    pass


def fake_serial_module(script):
    """script: 바이트(그대로 읽힘), ('gap', 초)(그동안 아무것도 안 옴), ('error',)(포트 오류)."""
    module = types.ModuleType("serial")

    class SerialException(OSError):
        pass

    class Serial:
        def __init__(self, *args, **kwargs):
            self.items = list(script)

        @property
        def in_waiting(self):
            return 0

        def read(self, n=1):
            if not self.items:
                raise Done()
            item = self.items[0]
            if isinstance(item, bytes):
                self.items.pop(0)
                return item
            if item[0] == "error":
                self.items.pop(0)
                raise SerialException("device disconnected")
            end = item[1]
            if isinstance(end, float) and end < 1e9:      # 처음 만났을 때 끝나는 시각으로 바꾼다
                self.items[0] = ("gap", time.time() + end)
                end = self.items[0][1]
            time.sleep(0.05)                               # 실제 timeout처럼 잠깐 기다리고 빈 값
            if time.time() >= end:
                self.items.pop(0)
            return b""

        def close(self):
            pass

        def open(self):
            pass

    module.Serial, module.SerialException = Serial, SerialException
    return module


def run_node(script, **extra_env):
    env = {"TRANSPORT": "http", "CSE_URL": "http://127.0.0.1:9/x", "RADAR_STALE_S": "0.3", **extra_env}
    out = io.StringIO()
    with patch.dict(os.environ, env), patch.dict(sys.modules, {"serial": fake_serial_module(script)}), \
            patch("subprocess.check_output", return_value=b"127.0.0.1\n"), contextlib.redirect_stdout(out):
        try:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        except Done:
            pass
    return re.findall(r">> alert: (\w+)", out.getvalue()), out.getvalue()


class RadarNodeUnknownTest(unittest.TestCase):
    def test_frame_gap_writes_unknown_then_recovers(self):
        alerts, log = run_node([frame(0, 400), ("gap", 0.6), frame(0, 400), frame()])
        self.assertEqual(alerts[:4], ["safe", "danger", "unknown", "danger"], log)
        self.assertIn("레이더 끊김", log)
        self.assertIn("레이더 복구", log)

    def test_engine_mode_writes_no_alert(self):
        # 엔진이 alert를 쓰는 모드에서는 이 노드가 alert를 쓰지 않는다 (작성자는 하나)
        alerts, log = run_node([frame(0, 400), ("gap", 0.6), frame()], RADAR_LOCAL_DECISION="0")
        self.assertEqual(alerts, [], log)

    def test_no_radar_at_start_is_unknown(self):
        alerts, _ = run_node([("gap", 0.6)])
        self.assertEqual(alerts, ["safe", "unknown"])

    def test_serial_error_writes_unknown_once(self):
        alerts, _ = run_node([frame(), ("error",), ("error",), frame(0, 2000)])
        self.assertEqual(alerts, ["safe", "unknown", "safe"])


if __name__ == "__main__":
    unittest.main()
