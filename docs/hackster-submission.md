# SafeZone Hackster Submission Draft

This draft reflects the recorded demo and the follow-up Pi check on 2026-11-20. It describes a risk-monitoring prototype, not a certified safety interlock. Add the recorded demo URL before submission.

## Short title

SafeZone: Camera–Radar Forklift Risk Monitoring

## Elevator pitch

Pi-based forklift monitoring fuses camera and radar, records DANGER via oneM2M, confirms worker ESP risk mode, and reports MEC health.

## Project story

### The idea

SafeZone is an edge IoT prototype for monitoring the space around a forklift. A Raspberry Pi combines LD2450 mmWave radar measurements with camera-based Vision output to estimate proximity risk and present the result to an operator. The project demonstrates sensing, risk assessment, oneM2M event history, and an ESP warning path. It does not claim a certified safety interlock or automatic forklift stop.

### How the data moves

The radar uploader reads LD2450 frames over UART and creates radar CINs in the Pi’s tinyIoT MN-CSE using the oneM2M MQTT binding. VisionAI reads a Logitech C270 camera and posts its latest `fusedTracks` CIN to the same resource tree over HTTP.

The RiskEngine runs as a separate Pi installation. It uses HTTP polling to retrieve the latest radar CIN and, when configured, the latest Vision CIN. It does not subscribe to radar over MQTT. It writes risk-event CINs over HTTP and posts alert state to the oneM2M alarm group. The live group contained the forklift, worker, and zone alert containers. After the worker AE was registered again, its new alert-container RI was restored in the group membership.

The configured SUB resources on the forklift and worker alert containers describe their notification routes. The worker SUB addresses `Cworker01`, which resolves through the worker AE’s point of access. The forklift SUB stores an HTTP `/notify` URL directly. During the follow-up check, DANGER was recorded in all three alert containers and the worker ESP entered risk mode. Both ESP boards were operating; this description does not claim that every output on both boards or an automatic vehicle stop was verified.

A separate bridge polls event data from the MN-CSE and writes compact history records to an IN-CSE running in Docker on a laptop. The Pi dashboard reads current state from the MN-CSE and history from the laptop IN-CSE. The Pi also runs a local IN-CSE, but the bridge and dashboard use the laptop instance.

### Why oneM2M and edge processing

The oneM2M resource tree gives the radar, Vision, event, and alert components a shared interface using AEs, containers, and content instances. MQTT carries radar CIN creation; the RiskEngine uses HTTP retrieval and writes; the group resource fans an alert out to member containers; SUB resources define notification destinations; and ACP resources define access rights. This keeps the sensing, decision, dashboard, and alarm resources connected through the CSE instead of relying on direct point-to-point calls between every component.

The Raspberry Pi hosts sensing and risk processing near the equipment. A MEC service-health IPE records the Vision input’s freshness and camera status as oneM2M state, helping an operator distinguish a missing camera result from a clear scene. That IPE reports service health; it does not make the risk decision. This build has not measured a latency improvement or verified that a separate ETSI MEC platform hosts the inference.

### What the demo and follow-up check showed

The recorded demo showed active camera–radar risk assessment. In the follow-up Pi check, the C270 was recognized, VisionAI created a fresh `fusedTracks` CIN with `cam_ok=true`, and the RiskEngine read Vision data as fresh. At that moment `tracks` was empty, so that run verified camera availability and the fresh-data path, not a positive person detection.

The RiskEngine created DANGER event records, and all three alert containers held DANGER state. The worker ESP entered risk mode after the worker registration and group membership were restored. A later read-only Pi check found no running Vision process and an older latest CIN; the engine then marked Vision stale. The latest DANGER observed in that later window was based on radar while Vision was stale, so it is not attributed to camera detection.

The Pi’s team-selected thresholds are WARNING at 2.5 m and DANGER at 1.5 m. The demo configuration used five-second radar freshness and target-association limits. These settings are demonstration values, not validated safety thresholds or a guarantee of tracking accuracy.

### Limitations

This prototype demonstrates risk monitoring and an observed worker ESP risk-mode notification. It does not demonstrate automatic forklift stopping, a safety-rated interlock, or industrial safety performance. The follow-up Vision run had no person tracks; persistent Vision operation, restart recovery, DHCP reservation, worst-case network delay, long-duration reliability, and measured MEC latency remain unverified.

The recorded demo video: **[add demo video URL]**.

## Cover image suggestion

Choose a clear frame from the recorded demo that shows the radar, Raspberry Pi, camera, and dashboard together. Keep the main equipment near the center so it remains visible after the 4:3 crop.

## Build details

- **Hardware:** Raspberry Pi, LD2450 mmWave radar, Logitech C270 camera, and two ESP8266 alarm nodes.
- **Software:** tinyIoT MN-CSE, Mosquitto, Python RiskEngine, VisionAI, MN-to-IN bridge, dashboard, MEC service-health IPE, and Docker IN-CSE.
- **Source:** https://github.com/extra-7ex/Sejong_4IoT_OneM2M/tree/codex/safezone-submission-20261120
- **Demo video:** pending link.
