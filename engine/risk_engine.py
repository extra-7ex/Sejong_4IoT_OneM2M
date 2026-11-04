"""Transport-independent radar CIN normalization and 2D relative-motion risk."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import time
from typing import Any, Callable, Optional

from .config import RiskConfig


class InputError(ValueError):
    """The latest radar data is malformed or cannot be interpreted."""


@dataclass(frozen=True)
class Target:
    key: str
    x_mm: float
    y_mm: float
    speed_cm_s_raw: Optional[float] = None


@dataclass(frozen=True)
class RadarFrame:
    sensor_ts_unix_s: Optional[float]
    targets: tuple[Target, ...]
    cin_ri: Optional[str] = None


def _json_object(value: Any, label: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InputError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise InputError(f"{label} must be a JSON object")
    return value


def normalize_radar_cin(message: Any) -> RadarFrame:
    """Accept a CSE CIN, its direct resource representation, or a SUB notification.

    Polling and a future HTTP notification callback both call this function,
    then pass the normalized frame to RiskEngine.process_frame().
    """
    root = _json_object(message, "message")

    # oneM2M notification: m2m:sgn.nev.rep.m2m:cin
    sgn = root.get("m2m:sgn")
    if sgn is not None:
        sgn = _json_object(sgn, "m2m:sgn")
        if sgn.get("vrq") is True:
            raise InputError("subscription verification request has no radar CIN")
        nev = _json_object(sgn.get("nev"), "m2m:sgn.nev")
        rep = _json_object(nev.get("rep"), "m2m:sgn.nev.rep")
        root = _json_object(rep.get("m2m:cin"), "notification CIN")
    elif "m2m:cin" in root:
        root = _json_object(root["m2m:cin"], "m2m:cin")

    if "con" not in root:
        raise InputError("CIN has no con")
    con = _json_object(root["con"], "CIN con")
    raw_ts = con.get("ts")
    sensor_ts = None
    if raw_ts is not None:
        try:
            sensor_ts = float(raw_ts)
        except (TypeError, ValueError) as exc:
            raise InputError("con.ts must be Unix seconds") from exc
        if not math.isfinite(sensor_ts):
            raise InputError("con.ts must be finite Unix seconds")

    raw_targets = con.get("targets")
    if not isinstance(raw_targets, list):
        raise InputError("con.targets must be an array (including [] for a valid empty frame)")
    targets: list[Target] = []
    for index, raw in enumerate(raw_targets[:3]):
        if not isinstance(raw, dict):
            raise InputError(f"targets[{index}] must be an object")
        try:
            x_mm, y_mm = float(raw["x"]), float(raw["y"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InputError(f"targets[{index}] requires numeric x and y in mm") from exc
        if not math.isfinite(x_mm) or not math.isfinite(y_mm):
            raise InputError(f"targets[{index}] coordinates must be finite")
        raw_speed = raw.get("v")
        try:
            speed = None if raw_speed is None else float(raw_speed)
        except (TypeError, ValueError) as exc:
            raise InputError(f"targets[{index}].v must be numeric cm/s") from exc
        # LD2450 slot/index is only a short-lived association hint, not a person ID.
        key = str(raw.get("slot", raw.get("id", index + 1)))
        targets.append(Target(key, x_mm, y_mm, speed))
    return RadarFrame(sensor_ts, tuple(targets), root.get("ri"))


class RiskEngine:
    def __init__(self, config: Optional[RiskConfig] = None, clock: Callable[[], float] = time.monotonic):
        self.config = config or RiskConfig()
        self.clock = clock
        self.history: dict[str, tuple[float, float, float]] = {}  # key -> rx(m), ry(m), receive-monotonic(s)
        self.last_receive_mono: Optional[float] = None
        self.last_receive_unix_s: Optional[float] = None
        self.last_sensor_ts: Optional[float] = None
        self.last_cin_ri: Optional[str] = None
        self.last_decision: Optional[dict[str, Any]] = None
        self.empty_since_mono: Optional[float] = None
        self.missing_track_since: dict[str, float] = {}
        self.input_fault: Optional[str] = "waiting_for_first_frame"

    def mark_input_fault(self, reason: str) -> dict[str, Any]:
        self.input_fault = reason
        self.history.clear()
        return self._unknown(reason)

    def process_message(self, message: Any, received_mono_s: Optional[float] = None) -> dict[str, Any]:
        try:
            frame = normalize_radar_cin(message)
        except InputError as exc:
            return self.mark_input_fault(str(exc))
        return self.process_frame(frame, received_mono_s)

    def process_frame(self, frame: RadarFrame, received_mono_s: Optional[float] = None) -> dict[str, Any]:
        received = self.clock() if received_mono_s is None else received_mono_s
        received_unix = time.time()
        self.last_receive_mono = received
        self.last_receive_unix_s = received_unix
        self.last_sensor_ts = frame.sensor_ts_unix_s
        self.last_cin_ri = frame.cin_ri
        self.input_fault = None

        if not frame.targets:
            if self.empty_since_mono is None:
                self.empty_since_mono = received
            empty_duration = received - self.empty_since_mono
            had_tracks = bool(self.history)
            if had_tracks and empty_duration < self.config.target_loss_grace_s:
                previous = self.last_decision or {}
                previous_status = previous.get("status")
                if previous_status in ("DANGER", "WARNING"):
                    return self._decision(
                        previous_status, "target_temporarily_missing_hold_previous_risk",
                        received, frame, targets=[], received_unix_s=received_unix, held=True,
                    )
                return self._decision("UNKNOWN", "target_temporarily_missing", received, frame, targets=[], received_unix_s=received_unix, held=True)
            self.history.clear()
            self.missing_track_since.clear()
            return self._decision("SAFE", "fresh_frame_has_no_targets", received, frame, targets=[], received_unix_s=received_unix)

        self.empty_since_mono = None
        incoming_keys = {target.key for target in frame.targets}
        missing_keys = set(self.history) - incoming_keys
        for key in incoming_keys:
            self.missing_track_since.pop(key, None)
        for key in list(self.missing_track_since):
            if received - self.missing_track_since[key] >= self.config.target_loss_grace_s:
                self.missing_track_since.pop(key, None)
        for key in missing_keys:
            self.missing_track_since.setdefault(key, received)
        uncertain_missing = [
            key for key, started in self.missing_track_since.items()
            if received - started < self.config.target_loss_grace_s
        ]
        # A fresh nonempty frame ends any empty-frame retention period.
        self.history = {k: v for k, v in self.history.items() if k in incoming_keys}
        evaluations = []
        next_history: dict[str, tuple[float, float, float]] = {}
        for target in frame.targets:
            rx, ry = target.x_mm / 1000.0, target.y_mm / 1000.0
            prior = self.history.get(target.key)
            velocity = None
            association_ok = True
            dt = None
            if prior:
                px, py, pt = prior
                dt = received - pt
                jump = math.hypot(rx - px, ry - py)
                if dt <= 0 or dt > self.config.max_sample_interval_s:
                    association_ok = False
                elif jump > self.config.max_target_jump_m:
                    association_ok = False
                else:
                    velocity = ((rx - px) / dt, (ry - py) / dt)
            next_history[target.key] = (rx, ry, received)
            evaluations.append(self._evaluate_target(target, rx, ry, velocity, dt, association_ok))

        self.history = next_history
        if uncertain_missing:
            previous_status = (self.last_decision or {}).get("status")
            held_status = previous_status if previous_status in ("DANGER", "WARNING") else "UNKNOWN"
            evaluations.append({
                "target": uncertain_missing[0], "status": held_status,
                "reason": "track_missing_hold_previous_risk" if held_status != "UNKNOWN" else "track_association_lost",
                "distance_m": None, "relative_velocity_mps": None, "sample_interval_s": None,
                "approaching": None, "t_cpa_s": None, "d_cpa_m": None,
                "cpa_valid": False, "association_valid": False, "held_previous_risk": held_status in ("DANGER", "WARNING"),
            })
        # Multi-target priority is DANGER > WARNING > UNKNOWN > SAFE.
        chosen = max(evaluations, key=lambda e: {"DANGER": 4, "WARNING": 3, "UNKNOWN": 2, "SAFE": 1}[e["status"]])
        return self._decision(
            chosen["status"], chosen["reason"], received, frame,
            targets=evaluations, primary=chosen, received_unix_s=received_unix,
        )

    def snapshot(self, now_mono_s: Optional[float] = None) -> dict[str, Any]:
        now = self.clock() if now_mono_s is None else now_mono_s
        if self.last_receive_mono is None:
            return self._unknown(self.input_fault or "waiting_for_first_frame")
        age = now - self.last_receive_mono
        if age > self.config.stale_after_s:
            return self._unknown("radar_input_stale", age_s=age)
        if self.last_decision is not None:
            return self.last_decision
        return self._unknown("no_decision")

    def _evaluate_target(self, target: Target, rx: float, ry: float,
                         velocity: Optional[tuple[float, float]], dt: Optional[float],
                         association_ok: bool) -> dict[str, Any]:
        distance = math.hypot(rx, ry)
        t_cpa = d_cpa = None
        approaching = None
        cpa_valid = False
        reason = "outside_test_thresholds"
        if distance <= self.config.danger_distance_m:
            status, reason = "DANGER", "current_distance_danger"
        elif distance <= self.config.warning_distance_m:
            status, reason = "WARNING", "current_distance_warning"
        else:
            status = "SAFE"
        if not association_ok and status == "SAFE":
            status, reason = "UNKNOWN", "target_association_uncertain"
        if velocity is not None and association_ok:
            vx, vy = velocity
            v2 = vx * vx + vy * vy
            if v2 > self.config.min_speed_mps ** 2:
                dot = rx * vx + ry * vy
                approaching = dot < 0
                candidate_t = -dot / v2
                if approaching and 0 <= candidate_t <= self.config.cpa_horizon_s:
                    t_cpa = candidate_t
                    d_cpa = math.hypot(rx + vx * t_cpa, ry + vy * t_cpa)
                    cpa_valid = True
                    # t_cpa is time of closest approach, not first entry into cpa_radius_m.
                    # MVP judges predicted closest distance within the horizon; it does not
                    # calculate the boundary-crossing time of the radius.
                    if d_cpa <= self.config.cpa_radius_m and t_cpa <= self.config.danger_ttc_s:
                        status, reason = "DANGER", "predicted_cpa_inside_radius_within_danger_time"
                    elif d_cpa <= self.config.cpa_radius_m and t_cpa <= self.config.warning_ttc_s:
                        if status != "DANGER":
                            status, reason = "WARNING", "predicted_cpa_inside_radius_within_warning_time"
        return {
            "target": target.key,
            "distance_m": round(distance, 4),
            "relative_velocity_mps": None if velocity is None else [round(velocity[0], 4), round(velocity[1], 4)],
            "sample_interval_s": None if dt is None else round(dt, 4),
            "approaching": approaching,
            "t_cpa_s": None if t_cpa is None else round(t_cpa, 4),
            "d_cpa_m": None if d_cpa is None else round(d_cpa, 4),
            "cpa_valid": cpa_valid,
            "association_valid": association_ok,
            "speed_cm_s_raw": target.speed_cm_s_raw,
            "status": status,
            "reason": reason,
        }

    def _decision(self, status: str, reason: str, received: float, frame: RadarFrame,
                  targets: list[dict[str, Any]], primary: Optional[dict[str, Any]] = None,
                  held: bool = False, received_unix_s: Optional[float] = None) -> dict[str, Any]:
        decision = {
            "schema": "safezone.risk-event.v1",
            "status": status,
            "level": {"SAFE": "safe", "WARNING": "warn", "DANGER": "danger", "UNKNOWN": "unknown"}[status],
            "reason": reason,
            "source": "AE-forklift01/radar",
            "cin_ri": frame.cin_ri,
            "sensor_ts_unix_s": frame.sensor_ts_unix_s,
            "server_received_at_unix_s": received_unix_s,
            "server_received_at_utc": None if received_unix_s is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(received_unix_s)),
            "event_created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "calculation_time_basis": "server_monotonic_receive_time",
            "target_count": len(targets),
            "targets": targets,
            "held_previous_risk": held,
            "assumptions": {
                "coordinate_frame": "radar_fixed_2d_mm",
                "radar_heading_constant": True,
                "velocity_source": "finite_difference_of_same_slot_xy_using_server_monotonic_receive_time",
                "sensor_ts_usage": "metadata_only_never_mixed_with_receive_time",
                "cpa_meaning": "closest_approach_time_and_distance_under_constant_relative_velocity",
                "risk_radius_m_is_hypothesis": True,
            },
            "parameters": {
                "warning_distance_m": self.config.warning_distance_m,
                "danger_distance_m": self.config.danger_distance_m,
                "cpa_radius_m": self.config.cpa_radius_m,
                "warning_t_cpa_s": self.config.warning_ttc_s,
                "danger_t_cpa_s": self.config.danger_ttc_s,
                "cpa_horizon_s": self.config.cpa_horizon_s,
                "stale_after_s": self.config.stale_after_s,
                "target_loss_grace_s": self.config.target_loss_grace_s,
            },
        }
        if primary:
            for key in ("distance_m", "relative_velocity_mps", "sample_interval_s", "approaching", "t_cpa_s", "d_cpa_m", "cpa_valid"):
                decision[key] = primary[key]
        self.last_decision = decision
        return decision

    def _unknown(self, reason: str, age_s: Optional[float] = None) -> dict[str, Any]:
        decision = {
            "schema": "safezone.risk-event.v1", "status": "UNKNOWN", "level": "unknown",
            "reason": reason, "source": "AE-forklift01/radar", "sensor_ts_unix_s": self.last_sensor_ts,
            "server_received_at_unix_s": self.last_receive_unix_s,
            "server_received_at_utc": None if self.last_receive_unix_s is None else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.last_receive_unix_s)),
            "event_created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "calculation_time_basis": "server_monotonic_receive_time", "targets": [],
            "held_previous_risk": False,
            "parameters": {
                "warning_distance_m": self.config.warning_distance_m,
                "danger_distance_m": self.config.danger_distance_m,
                "cpa_radius_m": self.config.cpa_radius_m,
                "warning_t_cpa_s": self.config.warning_ttc_s,
                "danger_t_cpa_s": self.config.danger_ttc_s,
                "cpa_horizon_s": self.config.cpa_horizon_s,
                "stale_after_s": self.config.stale_after_s,
                "target_loss_grace_s": self.config.target_loss_grace_s,
            },
        }
        if age_s is not None:
            decision["input_age_s"] = round(age_s, 4)
        self.last_decision = decision
        return decision
