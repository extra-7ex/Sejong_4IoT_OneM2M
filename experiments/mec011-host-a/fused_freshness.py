"""Experiment only: assess whether a fusedTracks CIN is usable; never controls risk."""
import json
import math


def assess(cin, now_s, max_age_s=3.0, max_future_skew_s=0.5):
    """Assumes ts is capture time in Unix seconds and clocks are synchronized.

    Thresholds are illustrative; OK means the envelope passed these checks only.
    """
    if not all(math.isfinite(x) and x >= 0 for x in (now_s, max_age_s, max_future_skew_s)):
        raise ValueError('invalid time configuration')
    try:
        con = cin['m2m:cin']['con']
        data = json.loads(con) if isinstance(con, str) else con
        if not isinstance(data, dict):
            return 'INVALID'
        ts, cam_ok, tracks = data.get('ts'), data.get('cam_ok'), data.get('tracks')
        if isinstance(ts, bool) or not isinstance(ts, (int, float)) or not math.isfinite(ts):
            return 'INVALID'
        if not isinstance(cam_ok, bool) or not isinstance(tracks, list) or not all(isinstance(t, dict) for t in tracks):
            return 'INVALID'
    except (KeyError, TypeError, json.JSONDecodeError):
        return 'INVALID'
    age = now_s - ts
    if age < -max_future_skew_s:
        return 'CLOCK_UNCERTAIN'
    if age > max_age_s:
        return 'STALE'
    if not cam_ok:
        return 'CAMERA_UNAVAILABLE'
    return 'OK'
