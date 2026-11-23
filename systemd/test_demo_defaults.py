"""Cross-check the default services against the engine and radar configuration."""

import os
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch

from engine.config import RiskConfig, one_m2m_config

ROOT = Path(__file__).resolve().parent


def environment(service):
    values = {}
    for line in (ROOT / service).read_text(encoding="utf-8").splitlines():
        if line.startswith("Environment="):
            for item in shlex.split(line.partition("=")[2]):
                name, value = item.split("=", 1)
                values[name] = value
    return values


class DemonstrationDefaults(unittest.TestCase):
    def test_engine_settings_and_single_alert_writer(self):
        engine = environment("safezone-engine.service")
        radar = environment("safezone-radar.service")
        with patch.dict(os.environ, engine, clear=True):
            risk = RiskConfig.from_env()
            one_m2m = one_m2m_config()
        self.assertEqual((risk.danger_distance_m, risk.warning_distance_m), (1.5, 2.5))
        self.assertEqual((risk.stale_after_s, risk.max_sample_interval_s), (5, 5))
        self.assertEqual(one_m2m["origin"], "Criskengine")
        self.assertEqual(radar["RADAR_LOCAL_DECISION"], "0")
        args = shlex.split(engine["ENGINE_ARGS"])
        self.assertEqual(args[args.index("--transport") + 1], "polling")
        self.assertEqual(args[args.index("--vision-path") + 1], "/AE-VisionAI/fusedTracks/la")
        self.assertEqual(args[args.index("--alert-path") + 1], "/grp-safezone-alarms/fopt")

    def test_ipe_uses_discovery_and_dedicated_origin(self):
        values = environment("safezone-ipe.service")
        with patch.dict(os.environ, values, clear=True):
            from onem2m.mec_ipe import load_config
            config = load_config()
        self.assertEqual(config["probe"], "mec-cin")
        self.assertEqual(config["read_origin"], "CmecIPE")
        self.assertEqual(config["mec_service"], "safezone-vision-cin-trial")
        self.assertTrue(config["mec_base"].startswith("http://127.0.0.1:18080/"))

    def test_bridge_requires_external_in_address(self):
        values = environment("safezone-bridge.service")
        self.assertEqual(values["BRIDGE_MN_ORIGIN"], "Cbridge")
        self.assertEqual(values["BRIDGE_IN_BASE"], "")
        unit = (ROOT / "safezone-bridge.service").read_text(encoding="utf-8")
        self.assertIn("ExecStartPre=/usr/bin/test -n ${BRIDGE_IN_BASE}", unit)


if __name__ == "__main__":
    unittest.main()
