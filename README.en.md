=
# SafeZone: Forklift–Pedestrian Safety on oneM2M and ETSI MEC

Team 4IoT (Sejong University) · 2026 oneM2M International Hackathon
Hackster article: (paste the public Hackster URL here)

## What it does

- An HLK-LD2450 24 GHz mmWave radar watches the forklift's blind spot without requiring workers to wear tags.
- VisionAI (Ultralytics YOLO pose on a Logitech C270) confirms people and their posture. The camera can raise risk but never lower it.
- The RiskEngine decides SAFE / WARNING (2.5 m) / DANGER (1.5 m) / UNKNOWN (no fresh radar data for 5 s), predicts the closest point of approach, and releases to SAFE only after 3 s.
- One alert written to the oneM2M group `grp-safezone-alarms/fopt` reaches the forklift alarm, the worker tag and the zone alert container.
- Forklift alarm node (ESP8266 + SG90 servo + buzzer): WARNING beeps slowly while the fork keeps moving, DANGER stops the fork, UNKNOWN also stops it with a slow beep.
- Worker tag (ESP8266): registers itself as `AE-worker01` on boot, is found by the label `type:worker-alarm`, and sends a 30 s heartbeat.
- Dashboard: live state from the MN-CSE and event history from the IN-CSE.
- MEC: an IPE publishes the VisionAI service health as oneM2M data, and `experiments/mec011-host-a` covers MEC 011 service registration and discovery.

## Architecture

    LD2450 --UART--> radar node (IPE) --MQTT--> tinyIoT MN-CSE (Raspberry Pi 4)
    C270 --USB--> VisionAI --HTTP--> MN-CSE <--HTTP--> RiskEngine
    RiskEngine --> grp-safezone-alarms/fopt --> alert containers --SUB/notify (HTTP)--> forklift alarm, worker tag
    MN-CSE --Mcc--> IN-CSE (laptop) <-- bridge AE (events) ; dashboard reads MN + IN

## Repository layout

| Path | Contents |
|---|---|
| `radar/` | LD2450 uploader `radar_node.py`, simulated radar `sim_rader.py` |
| `engine/` | RiskEngine: distance, CPA, camera fusion rules, SAFE release delay |
| `vision/` | VisionAI: camera person/pose detection, floor mapping, radar fusion (AGPL-3.0) |
| `onem2m/` | MN→IN bridge, MEC service-health IPE, alarm group, subscription scripts, `tinyiot-patches/` |
| `dashboard/` | Monitoring dashboard |
| `esp8266/` | Forklift alarm node `alert_node.ino`, worker tag `worker_node.ino` |
| `systemd/` | Demo services (`safezone.target`) |
| `tools/preflight.py` | Pre-demo check: services, data freshness, dead subscriptions |
| `experiments/mec011-host-a/` | MEC 011 registration and discovery experiment |
| `docs/` | Architecture, data format, CSE naming, runbook, wiring diagrams |

## Quick start (Raspberry Pi)

    sudo systemctl start mosquitto tinyiot-mn
    sudo systemctl start safezone.target        # radar, engine, bridge, dashboard, IPE
    python3 tools/preflight.py --fix            # check data and remove dead subscriptions
    bash onem2m/sub_alert_node.sh <forklift-esp-ip>

ESP8266 firmware: copy `secrets.example.h` to `secrets.h`, set Wi-Fi (and `CSE_HOST` for the worker tag), then flash with Arduino IDE (board: NodeMCU 1.0, ESP8266 core 3.1.2, ArduinoJson 7). The full step-by-step guide is in `시연방법.md` (Korean).

## Wiring

- [Radar node: LD2450 → Raspberry Pi UART](docs/Schematics%20and%20circuit%20diagrams/1_radar_pi_uart.png)
- [Forklift alarm node](docs/Schematics%20and%20circuit%20diagrams/2_forklift_alarm_node.png)
- [Worker alarm tag](docs/Schematics%20and%20circuit%20diagrams/3_worker_alarm_tag.png)

## License

Source code is Apache 2.0, except `vision/`, which is AGPL-3.0 because it uses Ultralytics YOLO11. Non-code content is CC BY 4.0.
