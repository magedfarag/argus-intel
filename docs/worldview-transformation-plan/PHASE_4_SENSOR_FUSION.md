# Phase 4: Sensor Fusion And Simulator Modes

## Objective

Add the simulator-style multi-sensor inspection layer: thermal, night vision, low-light, CCTV/video abstraction, and synchronized scene playback.

## Entry Criteria

- Phase 3 exit criteria met

## Exit Criteria

- Sensor viewing modes exist and are usable
- Camera/video abstraction exists with time sync
- Users can inspect an incident across scene, map, and video-style views

## Track A: Render Modes

- `[x]` Define render mode architecture for day, low-light, night vision, and thermal
- `[x]` Implement scene mode switching
- `[x]` Add legend and UI affordances for mode context
- `[x]` Define which modes are visual simulation only versus data-backed

## Track B: Camera And Video Abstraction

- `[x]` Define `camera_observation` or equivalent model
- `[x]` Design georegistration approach for fixed and mobile cameras
- `[x]` Define media metadata contract for clip references and timestamps
- `[x]` Build a first playback-capable camera feed panel

## Track C: Multi-View Time Synchronization

- `[x]` Sync map, scene, timeline, and camera playback to one playhead
- `[x]` Add incident-follow workflows between views
- `[x]` Preserve selection state when jumping across views
- `[x]` Add replay tests for synchronized incidents

## Track D: Detection Overlays

- `[x]` Define ground-object detection overlay contract
- `[x]` Add first detection layer in scene or camera views
- `[x]` Link detections back to the evidence model
- `[x]` Define confidence and provenance handling for detections

## Suggested Subagent Split

- Subagent 1: Track A
- Subagent 2: Track B
- Subagent 3: Track D
- Main thread or Subagent 4: Track C after Tracks A and B are stable

## Notes

- Keep explicit separation between visual simulation and validated sensor data.
- Do not hide provenance limitations from the user.
