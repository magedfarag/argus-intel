# Program Overview

## Goal

Deliver a replayable, multi-sensor intelligence platform that combines:

- imagery
- ship and aircraft tracks
- satellite orbits and passes
- airspace/no-fly restrictions
- strike and jamming events
- 3D scene inspection
- sensor/video viewpoints
- investigation and evidence workflows

## What the current repo already gives us

- AOI CRUD and timeline-oriented workflows
- imagery search and compare
- GDELT context
- ship and aircraft playback primitives
- a 2D map and a globe surface
- dark-ship, chokepoint, and briefing concepts

## What this program adds

- durable snapshotting of volatile feeds
- one historical timeline across all source families
- article-specific operational layers
- a true 3D world model instead of a stylized globe
- sensor-mode and camera/video integration
- investigation-grade analyst workflows

## Non-goals for early phases

- global real-time coverage guarantees
- premium provider lock-in before public-source workflows prove value
- full ML-based object detection across every source family
- large-scale warehouse or lakehouse architecture
- full CCTV-at-scale ingestion in the first pilot

## Success metrics

### Technical

- frontend typecheck and backend test gates remain green at every phase
- replay queries work for 24h, 7d, and 30d windows from persisted data
- every displayed layer has provenance and event-time semantics
- no split-brain between event stores used by playback and ingestion

### User-facing

- analyst can reconstruct an incident in one synchronized timeline
- analyst can turn on/off layers without breaking temporal alignment
- analyst can inspect a scene in both 2D and 3D
- analyst can export an evidence-backed case package

## Release cutlines

| Release | Included phases | Outcome |
|---|---|---|
| Pilot 1 | 0-2 | Stable replayable operational timeline with article-specific layers on the current map/globe stack |
| Pilot 2 | 0-4 | 3D world plus sensor/video-style workflows for bounded scenarios |
| Production | 0-6 | Hardening, governance, performance, and operational controls |

## Core sequencing rule

Do not build “spy simulator” visuals before the data plane is trustworthy. The critical path is:

```text
stabilize current branch
    ->
unify storage + replay
    ->
add operational layers
    ->
upgrade 3D scene
    ->
add sensor/video fusion
    ->
add investigation workflows
    ->
production hardening
```

## Program-level risks

- current branch regressions mask real progress unless Phase 0 is completed first
- adding new event families without freezing contracts will stall parallel work
- 3D stack migration can consume the roadmap if started before the data plane is done
- video/sensor work can become a sink without bounded pilot scenarios
- LLM features can outrun data quality and provenance if introduced too early
