"""Validate fresh Vision observations and apply the agreed conservative fusion rules.

Rules (VisionAI only advises; the radar decision stays the base):
1. camera_only + raise on a radar SAFE decision -> WARNING (person the radar missed).
2. confirmed + raise with a risky posture on a radar WARNING target -> DANGER (crouching or lying worker).
3. ghost_suspect + lower_to_caution on a radar DANGER target -> WARNING, never SAFE, only when
   the target is farther than ``ghost_min_distance_m`` and Vision is at most ``lower_max_age_s`` old.

Rules 2 and 3 touch one radar target. A Vision track belongs to a radar target only when its
``radar_id`` equals the radar slot and its ``dist_m`` is within ``match_tolerance_m`` of the
engine's distance, so a reshuffled slot cannot lower or raise the wrong target.
"""

from __future__ import annotations

import json
import math
from typing import Any

SEVERITY = {"SAFE": 1, "UNKNOWN": 2, "WARNING": 3, "DANGER": 4}
LEVEL = {"SAFE": "safe", "WARNING": "warn", "DANGER": "danger", "UNKNOWN": "unknown"}
RISKY_POSTURES = ("crouching", "lying")


def assess(cin: Any, received_mono_s: float, received_unix_s: float,
           max_age_s: float = 3.0, max_future_skew_s: float = 0.5) -> dict:
    """Return an observation status, its age and the validated tracks."""
    try:
        resource = cin.get("m2m:cin", cin)
        con = resource["con"]
        payload = json.loads(con) if isinstance(con, str) else con
        if not isinstance(payload, dict):
            raise ValueError("Vision con must be an object")
        timestamp = payload.get("ts")
        cam_ok = payload.get("cam_ok")
        tracks = payload.get("tracks")
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or not math.isfinite(timestamp):
            raise ValueError("Vision ts must be finite Unix seconds")
        if not isinstance(cam_ok, bool) or not isinstance(tracks, list):
            raise ValueError("Vision cam_ok and tracks are required")
        if not all(isinstance(track, dict) for track in tracks):
            raise ValueError("Vision tracks must contain objects")
        age = received_unix_s - timestamp
        base = {"ri": resource.get("ri"), "age_s": round(age, 3)}
        if age < -max_future_skew_s:
            return {"status": "clock_uncertain", **base, "raise_warning": False, "tracks": []}
        if age > max_age_s:
            return {"status": "stale", **base, "raise_warning": False, "tracks": []}
        if not cam_ok:
            return {"status": "camera_unavailable", **base, "raise_warning": False, "tracks": []}
        raise_warning = any(track.get("state") == "camera_only" and track.get("advice") == "raise"
                            for track in tracks)
        return {"status": "fresh", **base, "raise_warning": raise_warning, "tracks": tracks}
    except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": str(exc), "raise_warning": False, "tracks": []}


def _slot(key: Any) -> int | None:
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


def _matching_track(evaluation: dict, tracks: list[dict], state: str, advice: str,
                    match_tolerance_m: float) -> dict | None:
    """Vision track for this radar target: same slot and a consistent distance."""
    slot = _slot(evaluation.get("target"))
    distance = evaluation.get("distance_m")
    if slot is None or not isinstance(distance, (int, float)):
        return None
    for track in tracks:
        if track.get("state") != state or track.get("advice") != advice:
            continue
        if _slot(track.get("radar_id")) != slot:
            continue
        track_distance = track.get("dist_m")
        if not isinstance(track_distance, (int, float)) or isinstance(track_distance, bool):
            continue
        if abs(track_distance - distance) <= match_tolerance_m:
            return track
    return None


def apply_radar_advice(decision: dict, observation: dict, lower_max_age_s: float = 1.0,
                       ghost_min_distance_m: float = 1.0, match_tolerance_m: float = 0.5) -> dict:
    """Combine one radar decision with one Vision observation."""
    result = dict(decision)
    result["vision"] = {key: value for key, value in observation.items()
                        if key not in ("raise_warning", "tracks")}
    if observation.get("status") != "fresh" or decision.get("status") == "UNKNOWN":
        return result

    tracks = observation.get("tracks") or []
    age = observation.get("age_s")
    lower_allowed = isinstance(age, (int, float)) and age <= lower_max_age_s
    adjustments = []
    evaluations = []
    for evaluation in decision.get("targets") or []:
        adjusted = dict(evaluation)
        status = evaluation.get("status")
        held = evaluation.get("held_previous_risk") or evaluation.get("association_valid") is False
        if status == "WARNING" and not held:
            track = _matching_track(evaluation, tracks, "confirmed", "raise", match_tolerance_m)
            if track is not None and track.get("posture") in RISKY_POSTURES:
                adjusted.update(status="DANGER", reason="vision_risky_posture_raise",
                                radar_status=status, vision_posture=track.get("posture"))
                adjustments.append({"target": evaluation.get("target"), "from": status, "to": "DANGER",
                                    "rule": "posture_raise", "posture": track.get("posture")})
        elif status == "DANGER" and not held and lower_allowed:
            distance = evaluation.get("distance_m")
            track = _matching_track(evaluation, tracks, "ghost_suspect", "lower_to_caution", match_tolerance_m)
            if track is not None and isinstance(distance, (int, float)) and distance > ghost_min_distance_m:
                adjusted.update(status="WARNING", reason="vision_ghost_suspect_lowered", radar_status=status)
                adjustments.append({"target": evaluation.get("target"), "from": status, "to": "WARNING",
                                    "rule": "ghost_lower", "distance_m": distance})
        evaluations.append(adjusted)

    if adjustments:
        chosen = max(evaluations, key=lambda e: SEVERITY.get(e.get("status"), 2))
        result["targets"] = evaluations
        result["radar_status"] = decision.get("status")
        result["status"] = chosen["status"]
        result["level"] = LEVEL[chosen["status"]]
        result["reason"] = chosen.get("reason", result.get("reason"))

    if result.get("status") == "SAFE" and observation.get("raise_warning"):
        result.setdefault("radar_status", decision.get("status"))
        result["status"] = "WARNING"
        result["level"] = "warn"
        result["reason"] = "vision_camera_only_raise"
        adjustments.append({"target": None, "from": "SAFE", "to": "WARNING", "rule": "camera_only_raise"})

    if adjustments:
        result["vision_adjustments"] = adjustments
    return result


class ReleaseHold:
    """Keep the last WARNING/DANGER until SAFE has lasted ``hold_s`` seconds (team restart rule).

    Only a fall to SAFE is delayed; DANGER -> WARNING and every rise pass at once. UNKNOWN passes
    unchanged so that radar loss is never hidden behind an older risk.
    """

    def __init__(self, hold_s: float = 3.0):
        self.hold_s = hold_s
        self.last_risk_status: str | None = None
        self.safe_since: float | None = None

    def apply(self, decision: dict, now_mono_s: float) -> dict:
        status = decision.get("status")
        if status in ("WARNING", "DANGER"):
            self.last_risk_status = status
            self.safe_since = None
            return decision
        if status != "SAFE":
            self.safe_since = None  # UNKNOWN interrupts the SAFE streak; risk memory stays
            return decision
        if self.last_risk_status is None or self.hold_s <= 0:
            return decision
        if self.safe_since is None:
            self.safe_since = now_mono_s
        safe_for = now_mono_s - self.safe_since
        if safe_for >= self.hold_s:
            self.last_risk_status = None
            self.safe_since = None
            return decision
        held = dict(decision)
        held.update(status=self.last_risk_status, level=LEVEL[self.last_risk_status],
                    reason="release_hold_waiting_for_safe", released_status="SAFE",
                    release_reason=decision.get("reason"),
                    safe_for_s=round(safe_for, 3), release_hold_s=self.hold_s)
        return held
