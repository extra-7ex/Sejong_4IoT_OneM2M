"""설정 읽기 — 무거운 라이브러리(cv2, ultralytics) 없이 쓸 수 있게 main.py에서 분리했다.

config.pi.yaml은 `base: config.yaml` 위에 다른 값만 적고, config.local.yaml(git 제외: CSE 주소 등)이 마지막에 덮어쓴다.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]   # vision4iot/ (config.yaml 위치)


def merge(base, over):
    """over의 값으로 base를 덮어쓴다(dict는 안쪽까지). 둘 다 바꾸지 않고 새 dict를 돌려준다."""
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path, local=True):
    """`base: config.yaml`이 있으면 그 위에 이 파일 값만 덮어쓴다 (config.pi.yaml은 다른 점만 적는다).
    마지막으로 config.local.yaml(git 제외: CSE 주소 등)이 있으면 그 값을 덮어쓴다."""
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if base := cfg.pop("base", None):
        cfg = merge(load_config(path.parent / base, local=False), cfg)   # base는 이 파일 옆 기준
    if local and (lp := path.parent / "config.local.yaml").exists() and lp != path:
        cfg = merge(cfg, load_config(lp, local=False))
    return cfg


def resolve(p):
    """config의 상대 경로는 프로젝트 폴더 기준."""
    p = Path(p)
    return str(p if p.is_absolute() else ROOT / p)
