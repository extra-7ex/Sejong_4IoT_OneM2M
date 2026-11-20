# Hackster submission working copy

## Basics tab — separate fields, not part of Story

**Short title**

SafeZone: Camera–Radar Fusion for Forklift Safety

**Elevator pitch**

A Pi-based forklift model combines radar and camera inputs with oneM2M alerts, worker warnings, and an SG90 fork stop.

## Story field — paste only the sections below

### The problem and who we build for

Forklift traffic often shares work areas with pedestrians, and visibility can be limited by the truck, its load, and the aisle layout. In a September 2025 fatality alert, South Korea’s Ministry of Employment and Labor listed three forklift-related deaths reported within two weeks. One worker was killed after being caught between a parked truck and a reversing forklift. OSHA’s forklift guidance also notes that driver visibility can be limited by blind spots and recommends visibility aids such as spotters. These reports describe the hazard; they do not show that a sensor prototype alone can prevent such incidents. ([Ministry of Employment and Labor, 18 Sep 2025](https://www.moel.go.kr/local/jinju/news/notice/noticeView.do?bbs_seq=20250900815); [OSHA pedestrian-traffic guidance](https://www.osha.gov/etools/powered-industrial-trucks/workplace/pedestrian-traffic))

SafeZone is aimed at warehouse and manufacturing-site safety teams where forklifts and pedestrians share aisles. The prototype explores two complementary cues: radar sensing that does not depend on a worker carrying a tag, and a wearable worker tag that can receive its own warning.

### What SafeZone does

SafeZone is an edge-IoT prototype built around a Raspberry Pi and a 3D-printed forklift model. The LD2450 watches the model’s rear blind spot. VisionAI processes a Logitech C270 camera, and the RiskEngine evaluates the available radar and configured Vision data into SAFE, WARNING, DANGER, or UNKNOWN states. oneM2M stores sensor data and events and routes alert state to the model’s alarm node and worker tag.

The forklift alarm node controls an SG90 servo and buzzer. In the dated model tests below, WARNING kept the fork moving with a slower beep, while DANGER stopped the fork and sounded a faster alarm. The worker tag provides a separate buzzer-and-LED warning. The servo moves the scale model’s fork; it does not control a full-size forklift’s drive motor.

### Model and system architecture

![SafeZone verified call flow and MEC011 target](safezone-architecture.svg)

The LD2450 connects to the Pi radar-collection IPE/MN-AE over UART. The uploader creates radar content instances (CINs) in the tinyIoT MN-CSE using MQTT. The C270 connects to VisionAI over USB; VisionAI writes `fusedTracks` CINs over HTTP. The RiskEngine polls the latest radar and configured Vision CINs over HTTP, then writes `events` and posts the alert state to `grp-safezone-alarms/fopt` over HTTP.

The current resource paths include `AE-forklift01/radar`, `AE-VisionAI/fusedTracks`, and `AE-riskengine/events`. The alarm group contains three alert containers: forklift, worker, and zone. A group `/fopt` write was verified to put DANGER in all three. The worker AE registers as `AE-worker01` with the `type:worker-alarm` label; its subscription uses `nu=Cworker01`, resolved through the AE’s point of access. The forklift subscription stores an HTTP `/notify` URL directly. Both device notification routes use Mca over HTTP.

Re-registering the worker AE created a new alert-container resource ID, so we restored that ID in the group’s `mid` list before retesting. The worker ACP currently gives `CAdmin` create, retrieve, and discovery permissions (mask 35); a least-privilege review remains open.

For history, a bridge AE polls events from the Pi MN-CSE and creates summaries in an IN-CSE running in Docker on a laptop. The dashboard reads current state from MN and event history from IN. The bridge uses HTTP/Mca calls to each CSE; it does not use a direct Mcc synchronization path. A separate local IN-CSE service also runs on the Pi but was not the bridge target in the 20 November deployment check.

### Edge software and MEC role

The Pi runs the radar uploader, RiskEngine, bridge, dashboard, and a service-health IPE. The IPE reads Vision freshness and `cam_ok`, then writes health state to oneM2M. It monitors Vision output; it does not process camera frames or make the risk decision. VisionAI itself uses Ultralytics YOLO pose inference and OpenCV.

The live Pi build did not verify an ETSI MEC platform performing Mp1/MEC011 service registration or discovery, and no MEC latency improvement was measured. In the architecture figure, the MN-CSE is mapped to the MEC App role in the competition reference diagram; the dotted Mp1/MEC011 link is a target integration.

### Hardware build

The model places the LD2450 behind a rear window. The forklift alarm node is a NodeMCU ESP8266 on an HW-389 board, powered by a 9 V battery, with an SG90 fork servo and buzzer. The worker tag is a second NodeMCU in a 3D-printed wearable case with a buzzer and LED window. On boot, its firmware registers its AE, ACP, alert and status containers, and subscription; the tag publishes a 30-second heartbeat. The Pi uses a 5 V, 3 A supply. Portable tests used a USB power bank.

### Software

The radar uploader, RiskEngine, VisionAI, bridge, dashboard, and service-health IPE are Python applications. tinyIoT provides the MN-CSE and IN-CSE, with Mosquitto for the radar MQTT binding; Docker runs the laptop IN-CSE. VisionAI uses Ultralytics YOLO pose inference and OpenCV. The ESP8266 nodes run Arduino firmware.

### Demo and results

The recorded demo shows the camera–radar risk path. The following results are from separate 2026 test runs; the settings should not be read as one combined profile.

- **15 November:** A team test uploaded radar frames, including empty frames, at about 0.5-second intervals. The HTTP alert-creation-and-notification path was measured at 0.00–0.12 seconds in that short run; the model fork stop and buzzer were observed.
- **16 November:** The worker-tag test covered automatic AE registration, `type:worker-alarm` discovery, and RiskEngine alert logging.
- **18 November:** The model alarm test used WARNING at 1.0 m and DANGER at 0.5 m. The reported behavior was a slower warning beep while the fork continued moving, followed by a stopped fork and faster buzzer in DANGER.
- **19 November:** Registrations and subscriptions were rebuilt over a phone hotspot. The Pi and both ESP nodes registered; the final end-to-end alarm result for that outdoor run was not recorded.
- **20 November Pi check:** The active RiskEngine used WARNING at 2.5 m, DANGER at 1.5 m, and five-second stale/association settings. The MQTT radar uploader showed 0.30–0.33-second responses at roughly 0.53-second intervals. DANGER was written to all three alert containers, and the worker ESP entered risk mode. The MQTT log and earlier HTTP measurement are from different runs, so they are not a direct performance comparison.

After the equipment was restored, the Pi recognized the C270. VisionAI was started manually from `/home/user/vision4iot`, created a fresh `fusedTracks` CIN, and the RiskEngine read it as fresh. `tracks` was empty in that run: it verified camera availability and the fresh-data path, not a positive person detection. Continuous Vision service operation was not verified.

### Lessons and limitations

The MQTT binding is used by the radar uploader; the RiskEngine, Vision output, ESP notifications, and MN-to-IN bridge use HTTP. On the Pi, the uploader waits for each MQTT response and skips new frames while one request is pending, avoiding a backlog of older frames. A separate lesson came from worker registration: a recreated AE may receive a new alert CNT resource ID, and the group membership must be updated to that ID.

The distance and five-second settings are team-selected demo values, not validated safety limits or tracking guarantees. The fresh Vision test had no person tracks, and continuous Vision operation, restart recovery, and long-duration reliability remain unverified. The model demonstrates a servo stop on a scale fork; it is not a certified vehicle interlock or a full-size forklift safety system. The MEC011 platform integration and the hotspot run’s final alarm outcome also remain unverified.

### Team

The team split work across radar and forklift-model hardware, worker-tag firmware and oneM2M registration, VisionAI and camera calibration, and Pi-side RiskEngine, CSE integration, bridge, dashboard, and service-health reporting.

## Submission assets — outside the Story field

- Source repository: https://github.com/extra-7ex/Sejong_4IoT_OneM2M/tree/codex/safezone-submission-20261120
- Add the recorded video in the separate video field and align its date, thresholds, transport, and IN-CSE location with the Story.
- Select a cover image for the separate 4:3 image field.
- The SVG above is an architecture figure. Add a photo or annotated view of the physical model if available.
- No electrical schematic was found in the reviewed project files; use an actual schematic PDF/PNG if the team has one.
