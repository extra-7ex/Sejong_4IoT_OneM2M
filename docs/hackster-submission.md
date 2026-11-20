# SafeZone Hackster Submission Draft

This draft describes the implementation and live checks recorded on 2026-11-20. Replace the video placeholder with the already recorded demo link before submission. The prototype should not be described as a certified or safety-rated system.

## Short title

SafeZone: Forklift Risk Monitoring with oneM2M

## Elevator pitch

Edge-based forklift risk monitoring with mmWave radar, oneM2M event history, and Vision service health reporting.

## Project story

### The idea

SafeZone is an edge IoT prototype for monitoring the space around a forklift. A Raspberry Pi reads target frames from an LD2450 mmWave radar and publishes them as oneM2M resources through a local tinyIoT MN-CSE. A RiskEngine polls the latest radar content, estimates target distance and relative motion, and records changes such as WARNING, DANGER, or UNKNOWN as event CINs.

### How the data moves

The deployed radar uploader runs on the Pi and sends radar CIN creation requests over the oneM2M MQTT binding. The deployed RiskEngine reads radar data through HTTP polling, then asks the MN-CSE to store event CINs over HTTP. A separate bridge polls the MN event stream and writes compact history records to an IN-CSE running in Docker on a laptop. The Pi dashboard reads live state from the MN and event history from the laptop IN-CSE.

The Pi also runs a small service-health IPE. It checks the latest Vision output and records whether it is fresh and usable. On the day documented here, the Vision service was stopped, the latest output was stale, and its camera status was false. The dashboard therefore showed Vision as inactive. That status check was running; live Vision inference was not.

### What we verified

During the deployment check, the Pi services were running, radar CINs were arriving, the RiskEngine received successful event-creation responses, and the bridge wrote event summaries to the laptop IN-CSE. The dashboard showed both MN and IN connections. The alert group, its member containers, and two subscription resources were present in the MN-CSE.

The RiskEngine and radar uploader have local changes that are included in this submission branch. The engine checks radar timestamps before accepting frames. On the Pi, WARNING and DANGER distance thresholds were set to 2.5 m and 1.5 m. Radar freshness and target association intervals were temporarily set to five seconds for the demo. These are team-selected demo settings, not validated safety thresholds or a guarantee of tracking accuracy.

### Limits of the prototype

The ESP alarm boards were powered off during the check. We did not verify alert delivery to the boards, buzzer or servo operation, automatic forklift stopping, or recovery after a full restart. The Vision service was inactive and had no fresh camera output. We have not verified DHCP reservation, worst-case network delay, long-duration reliability, or industrial safety performance.

The recorded demo video will be linked here: **[add demo video URL]**.

## Cover image suggestion

Choose a clear frame from the recorded demo that shows the radar setup, Raspberry Pi, and dashboard together. Keep the important objects near the center so they remain visible after the 4:3 crop.

## Build details to complete in the next form sections

- **Hardware:** Raspberry Pi, LD2450 mmWave radar, ESP8266 alarm nodes (alarm output unverified), camera (live Vision input unverified).
- **Software:** tinyIoT MN-CSE, Mosquitto, Python RiskEngine, MN-to-IN bridge, dashboard, service-health IPE, Docker IN-CSE.
- **Source:** https://github.com/extra-7ex/Sejong_4IoT_OneM2M
- **Demo video:** pending link.
