"""Validate fresh Vision observations and derive the agreed conservative advice."""

from __future__ import annotations

import json
import math
import time
from typing import Any


def assess(cin: Any, received_mono_s: float, received_unix_s: float,
           max_age_s: float = 3.0, max_future_skew_s: float = 0.5) -> dict:
    """Return an observation status and whether it supports raising SAFE to WARNING."""
    try:
        resource = cin.get("m2m:cin", cin)
        con = resource["con"]
        payload = json.loads(con) if isinstance(con, str) else con
        if not isinstance(payload, dict):
            raise ValueError("Vision con must be an object")
        timestamp = payload.get("ts")
        cam_ok = payload.get("cam_ok")
        radar_ok = payload.get("radar_ok")
        tracks = payload.get("tracks")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            raise ValueError("Vision ts must be finite Unix seconds")
        if not isinstance(cam_ok, bool) or not isinstance(tracks, list):
            raise ValueError("Vision cam_ok and tracks are required")
        if not all(isinstance(track, dict) for track in tracks):
            raise ValueError("Vision tracks must contain objects")
        age = received_unix_s - timestamp
        if age < -max_future_skew_s:
            return {"status": "clock_uncertain", "ri": resource.get("ri"), "age_s": round(age, 3), "raise_warning": False}
        if age > max_age_s:
            return {"status": "stale", "ri": resource.get("ri"), "age_s": round(age, 3), "raise_warning": False}
        if not cam_ok:
            return {"status": "camera_unavailable", "ri": resource.get("ri"), "age_s": round(age, 3), "raise_warning": False}
        if radar_ok is not True:
            return {"status": "vision_radar_unavailable", "ri": resource.get("ri"), "age_s": round(age, 3), "raise_warning": False}
        raise_warning = any(track.get("state") == "camera_only" and track.get("advice") == "raise"
                            for track in tracks)
        return {"status": "fresh", "ri": resource.get("ri"), "age_s": round(age, 3),
                "raise_warning": raise_warning}
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": str(exc), "raise_warning": False}


def apply_radar_advice(decision: dict, observation: dict) -> dict:
    """Apply only camera_only+raise to an otherwise SAFE radar decision."""
    result = dict(decision)
    result["vision"] = {key: value for key, value in observation.items() if key != "raise_warning"}
    if decision.get("status") == "SAFE" and observation.get("status") == "fresh" and observation.get("raise_warning"):
        result["status"] = "WARNING"
        result["level"] = "warn"
        result["reason"] = "vision_camera_only_raise"
    return result
