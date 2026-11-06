"""config.pi.yaml = config.yaml + 다른 값만."""
from vision4iot.config import load_config, merge


def test_merge_overrides_nested_keys_only():
    base = {"a": 1, "model": {"path": "x.pt", "imgsz": 640, "conf": 0.4}}
    out = merge(base, {"model": {"imgsz": 320}})
    assert out["model"] == {"path": "x.pt", "imgsz": 320, "conf": 0.4}
    assert base["model"]["imgsz"] == 640          # 원본은 그대로


def test_pi_config_inherits_laptop_config():
    lap, pi = load_config("config.yaml"), load_config("config.pi.yaml")
    assert pi["source"] == "webcam:0" and pi["headless"] is True
    assert pi["model"]["imgsz"] == 320
    assert pi["model"]["conf"] == lap["model"]["conf"]          # 안 적은 값은 config.yaml 것
    assert pi["thresholds"] == lap["thresholds"]
    assert pi["posture"] == lap["posture"]
    assert "base" not in pi


def test_local_config_overrides_last(tmp_path):
    (tmp_path / "config.yaml").write_text("onem2m:\n  base_url: ''\n  cse_name: TinyIoT\n", encoding="utf-8")
    (tmp_path / "config.pi.yaml").write_text("base: config.yaml\nsource: picam\n", encoding="utf-8")
    assert load_config(tmp_path / "config.pi.yaml")["onem2m"]["base_url"] == ""
    (tmp_path / "config.local.yaml").write_text("onem2m:\n  base_url: http://pi:3000\n", encoding="utf-8")
    cfg = load_config(tmp_path / "config.pi.yaml")
    assert cfg["onem2m"] == {"base_url": "http://pi:3000", "cse_name": "TinyIoT"}
    assert cfg["source"] == "picam"
