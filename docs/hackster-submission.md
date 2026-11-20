# Hackster submission working copy

## Basics tab — separate fields, not part of Story

**Short title**

SafeZone: Camera–Radar Fusion for Forklift Safety

**Elevator pitch**

A Pi-based forklift model combines radar and camera inputs with oneM2M alerts, worker warnings, and an SG90 fork stop.

## Story field — paste only the sections below

### Hook

SafeZone combines radar, camera-based pose analysis, and oneM2M alerts to demonstrate how a forklift safety system can warn a worker and stop a scale-model fork. Its recorded demo follows four cases: changing distance, camera–radar confirmation and posture risk, camera-AI loss, and radar loss.

### The problem

Forklift traffic often shares work areas with pedestrians, while the truck, its load, and aisle layout can limit visibility. In a September 2025 fatality alert, South Korea’s Ministry of Employment and Labor listed three forklift-related deaths reported within two weeks; one worker was caught between a parked truck and a reversing forklift. OSHA also notes that visibility can be limited by blind spots and recommends aids such as spotters. ([Ministry of Employment and Labor, 18 Sep 2025](https://www.moel.go.kr/local/jinju/news/notice/noticeView.do?bbs_seq=20250900815); [OSHA pedestrian-traffic guidance](https://www.osha.gov/etools/powered-industrial-trucks/workplace/pedestrian-traffic))

SafeZone is a prototype for warehouse and manufacturing teams exploring ways to add a warning layer where forklifts and pedestrians share space. Radar can detect without requiring a worker to carry a tag; the wearable tag adds a direct alert channel.

### How SafeZone works

![SafeZone architecture and verified call flow](safezone-architecture.svg)

An LD2450 radar connects to a Raspberry Pi over UART. A radar-collection IPE writes radar content instances (CINs) to the Pi’s tinyIoT MN-CSE over the oneM2M MQTT binding. A Logitech C270 connects to VisionAI over USB; VisionAI writes `fusedTracks` CINs to the same CSE over HTTP. The RiskEngine polls the latest radar and Vision data over HTTP, records decisions in `AE-riskengine/events`, and sends alert state to `grp-safezone-alarms/fopt`.

Three design choices shape the response:

1. **Radar provides the distance signal.** The current demo profile uses WARNING at 2.5 m and DANGER at 1.5 m.
2. **Vision can raise risk, never lower it.** A posture cue can raise WARNING to DANGER; camera evidence does not clear a radar warning.
3. **Radar loss fails safe on the model.** When radar data expires, the RiskEngine reports UNKNOWN and the scale-model fork moves to its stop position.

### Four cases in the demo

| Case | Input shown | Observed result |
|---|---|---|
| A — Distance stages | A radar target moves through the configured distance bands. | SAFE, WARNING, and DANGER states follow the demo thresholds; the model responds to the alert state. |
| B — Camera–radar fusion | VisionAI and radar confirm the same person. A crouched posture is then detected. | Risk rises from WARNING to DANGER with reason `vision_risky_posture_raise`. |
| C — Camera-AI interruption | VisionAI is stopped while the radar path remains available. | The camera adds no new evidence; loss of camera input does not lower an existing radar risk state. |
| D — Radar interruption | Radar updates stop and the input becomes stale. | State changes to UNKNOWN and the scale-model fork moves to its stop position. |

### oneM2M under the hood

SafeZone keeps sensor data, events, alerts, and subscriptions in oneM2M resources. The main paths are `AE-forklift01/radar`, `AE-VisionAI/fusedTracks`, and `AE-riskengine/events`. The worker AE registers with the `type:worker-alarm` label; label discovery lets the system find its alert resource without hard-coding the resource name. Its SUB uses `nu=Cworker01`, which the CSE resolves through the AE’s point of access. The forklift SUB stores an HTTP `/notify` endpoint directly.

During the recorded demo, a write to `/grp-safezone-alarms/fopt` appeared in all three alert containers: forklift, worker, and zone, and the worker ESP entered DANGER mode. In a later ACP retest, the three containers again showed `danger` records (`dist=1170`); that retest did not check ESP receipt or physical outputs. The zone alert container is a configured expansion point; this build has no physical zone beacon attached.

The Pi MN-CSE is registered with the laptop’s Docker IN-CSE over Mcc. Event-history transfer is a separate bridge AE: it polls events from MN and creates summaries in IN using HTTP/Mca. The dashboard reads current state from MN and history from IN. The operational MEC IPE discovers a Vision data service manually registered in the Pi-local MEC011 registry; its service record points to the actual oneM2M `fusedTracks/la` CIN. The IPE reads the latest CIN and records its freshness. While VisionAI was off, the service registration was `ACTIVE` but the data status was `INACTIVE`; briefly running VisionAI changed the data status from `INACTIVE` to `ACTIVE`. VisionAI was stopped after the test. Automatic service registration and address updates across edge devices, remote CSE discovery, and selection among multiple services remain future work.

### Hardware build

The prototype uses a 3D-printed forklift model with the LD2450 behind its rear window. A NodeMCU ESP8266 on an HW-389 board, powered by a 9 V battery, drives an SG90 servo on the model fork and a buzzer. A second NodeMCU is housed in a 3D-printed worker tag with a buzzer and LED window.

**Hardware:** HLK-LD2450 radar, Raspberry Pi 4B, Logitech C270 USB camera, two NodeMCU ESP8266 boards, SG90 servo, buzzers, 9 V battery, USB power bank, and a 5 V, 3 A power supply for the Raspberry Pi. The USB power bank was used for portable testing.

The servo moves the model’s fork. It does not control a full-size forklift’s drive motor or provide a certified vehicle interlock.

### Software and challenges solved

**Software:** Python, OpenCV, Ultralytics YOLO, Mosquitto, and Docker. Python runs the Pi-side applications; OpenCV and Ultralytics YOLO power VisionAI pose inference; Mosquitto provides the radar MQTT broker; Docker runs the laptop IN-CSE. The laptop dashboard reads current state from MN and event history from IN, while the ESP8266 nodes run Arduino firmware.

The radar uploader waits for each MQTT response and skips a new frame while a request is pending, preventing a backlog of older frames. We also restored the worker alert’s current group membership after re-registration assigned its alert container a new resource ID. These fixes keep the live path aligned with the latest sensor frame and active oneM2M resources.

### Limitations and next steps

The 2.5 m / 1.5 m thresholds and five-second freshness settings are team-selected demo values, not validated safety limits or tracking guarantees. In the post-demo Pi check, VisionAI was stopped after overheating and the stored `fusedTracks` data was stale; the camera–radar fusion above describes the recorded demo. The MEC011 discovery change is running in the Pi IPE, but its source branch is not yet included in the linked repository. Long-duration operation and restart recovery still need testing. The SG90 stop is demonstrated on a scale model, not a full-size vehicle. Automatic service registration, address updates, and selection across edge devices remain future work.

### Team

The team built the radar and forklift-model hardware, worker-tag firmware and oneM2M registration, VisionAI and camera setup, and the Pi-side RiskEngine, CSE integration, bridge, and service-status reporting.

## Submission assets — outside the Story field

- Source repository: https://github.com/extra-7ex/Sejong_4IoT_OneM2M/tree/codex/safezone-submission-20261120
- Add the recorded demo video in Hackster’s separate video field.
- Select a cover image for the separate 4:3 image field.
- The circuit diagram has been uploaded as a separate project asset.
- The SVG above is the architecture figure; add a photo of the physical model if available.
