"""Runtime assumptions and tunable MVP parameters.

All thresholds below are demonstration hypotheses, not validated safety limits.
The receive-time clock is monotonic and is the only clock used for velocity,
staleness, and track-loss timing. Sensor Unix timestamps are metadata only.
"""

from dataclasses import dataclass
import os


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None else float(value)


@dataclass(frozen=True)
class RiskConfig:
    warning_distance_m: float = 3.0
    danger_distance_m: float = 1.5
    warning_ttc_s: float = 3.0
    danger_ttc_s: float = 1.5
    cpa_radius_m: float = 1.0
    cpa_horizon_s: float = 3.0
    min_speed_mps: float = 0.05
    max_sample_interval_s: float = 0.75
    stale_after_s: float = 1.0
    target_loss_grace_s: float = 1.0
    max_target_jump_m: float = 2.5

    @classmethod
    def from_env(cls) -> "RiskConfig":
        return cls(
            warning_distance_m=_env_float("RISK_WARNING_DISTANCE_M", 3.0),
            danger_distance_m=_env_float("RISK_DANGER_DISTANCE_M", 1.5),
            warning_ttc_s=_env_float("RISK_WARNING_TTC_S", 3.0),
            danger_ttc_s=_env_float("RISK_DANGER_TTC_S", 1.5),
            cpa_radius_m=_env_float("RISK_CPA_RADIUS_M", 1.0),
            cpa_horizon_s=_env_float("RISK_CPA_HORIZON_S", 3.0),
            min_speed_mps=_env_float("RISK_MIN_SPEED_MPS", 0.05),
            max_sample_interval_s=_env_float("RISK_MAX_SAMPLE_INTERVAL_S", 0.75),
            stale_after_s=_env_float("RISK_STALE_AFTER_S", 1.0),
            target_loss_grace_s=_env_float("RISK_TARGET_LOSS_GRACE_S", 1.0),
            max_target_jump_m=_env_float("RISK_MAX_TARGET_JUMP_M", 2.5),
        )


def one_m2m_config() -> dict[str, str]:
    """Paths and identity are configurable so transport details stay replaceable."""
    return {
        "cse_base": os.getenv("ONEM2M_CSE_BASE", "http://127.0.0.1:3000/TinyIoT-MN").rstrip("/"),
        "radar_path": os.getenv("ONEM2M_RADAR_PATH", "/AE-forklift01/radar/la"),
        "events_path": os.getenv("ONEM2M_EVENTS_PATH", "/AE-riskengine/events"),
        "origin": os.getenv("ONEM2M_ORIGIN", "Criskengine"),
        "rvi": os.getenv("ONEM2M_RVI", "3"),
        "poll_interval_s": str(_env_float("ONEM2M_POLL_INTERVAL_S", 0.1)),
        "http_timeout_s": str(_env_float("ONEM2M_HTTP_TIMEOUT_S", 1.0)),
    }
