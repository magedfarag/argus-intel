# ARGUS — Maritime Intelligence Platform  
## Camera-Ready Demo Recording Script  
**Target audience**: Customers and management — executive, investor, and operator audiences  
**Target video length**: ~10 minutes (±10%)  
**Actual planned runtime**: 10 min 00 sec  
**Narration voice**: Native American English, professional broadcast tone, ~130 wpm  
**Prepared**: 2026-04-05 · **Revised**: 2026-04-09 (cinematic 3D/animation rewrite)

---

## PRE-FLIGHT CHECKLIST

| # | Task | Command / Action | Done |
|---|------|-----------------|------|
| 1 | Start backend server | `uvicorn app.main:app --reload` in repo root | ☐ |
| 2 | Start frontend dev server | `cd frontend && pnpm dev` (serves at `http://localhost:5173`) | ☐ |
| 3 | Confirm demo mode is active | Check console: `APP_MODE=demo` — no API key required | ☐ |
| 4 | Open browser to home page | Navigate to `http://localhost:5173` | ☐ |
| 5 | Confirm live clock shows UTC time | Header shows `● LIVE` + UTC timestamp | ☐ |
| 6 | Switch view mode to **3D Globe** | Click **🌐 3D** toggle (top-left of map canvas) — confirm dark CARTO globe renders | ☐ |
| 7 | Enable Maritime (AIS) and Aviation layers | Sensors panel → check **Maritime (AIS)** and **Aviation (ADS-B)** | ☐ |
| 8 | Click the **▶** play button (App toolbar) | Confirm 11 ship track trails animate across the Strait of Hormuz (no tracks crossing land) | ☐ |
| 9 | Switch Render Mode to **NIGHT VISION** | RenderModeSelector → **NIGHT VISION** — confirm green tint on globe | ☐ |
| 10 | Switch Render Mode back to **DAY** | RenderModeSelector → **DAY** before recording starts | ☐ |
| 11 | Set time range to **30d** preset | Click **▲** on Timeline slim-bar → expand → click **30d** button → collapse | ☐ |
| 12 | Create demo AOI (if not pre-seeded) | Zones panel → BBox drawing over Gulf region → name `Strait of Hormuz` | ☐ |
| 13 | Pre-create demo investigation | Cases panel → **+ New** → name: `Case-001 Dark Vessel Cluster` | ☐ |
| 14 | Ensure **3D** mode + **DAY** render mode | Confirm globe is in 3D view, DAY render, Maritime + Aviation layers enabled | ☐ |
| 15 | Record at 1920×1080 / 30 fps | OBS or screen recorder — maximize browser window, hide OS taskbar | ☐ |

### Key Demo Infrastructure
| Item | Value |
|------|-------|
| Frontend URL | `http://localhost:5173` |
| Globe tile style | CARTO Dark Matter (black globe, white coastlines — cinematic) |
| Ship vessels | 11 vessels with real TSS Hormuz sea-lane waypoints |
| Animation window | 30 hours of track data, 90 position reports per vessel |
| Timeline | Slim 40px bottom strip with event dots (click ▲ to expand to histogram) |
| Render modes | DAY / LOW LIGHT / NIGHT VISION / THERMAL |

---

## SCENE OVERVIEW

| # | Title | Cinematic Focus | T+ Start | T+ End | Duration |
|---|-------|----------------|----------|--------|----------|
| 01 | Opening Title Card | Static title overlay | T+0:00 | T+0:20 | 20 s |
| 02 | **3D Globe — Cinematic Open** | HERO: dark globe, rotate & zoom, track trails | T+0:20 | T+1:50 | **90 s** |
| 03 | **Animation Playback — Time Warp** | HERO: ship tracks in motion, speed × 4 | T+1:50 | T+2:50 | **60 s** |
| 04 | **Render Modes — Eyes of the Operator** | Night Vision → Thermal → Day | T+2:50 | T+3:25 | 35 s |
| 05 | Platform Home & Interface Orientation | UI overview, sidebar, timeline strip | T+3:25 | T+3:55 | 30 s |
| 06 | Zones — Define an Area of Interest | BBox draw, named AOI | T+3:55 | T+4:35 | 40 s |
| 07 | Dark Ships — AIS Gap Detection | Gap bars, sanctioned flag | T+4:35 | T+5:20 | 45 s |
| 08 | Vessel Profile Modal — Sanctions Screen | OFAC badge, vessel intel | T+5:20 | T+5:55 | 35 s |
| 09 | Briefing — AI Intelligence Assessment | Executive synthesis | T+5:55 | T+6:35 | 40 s |
| 10 | Routes — Chokepoint Monitoring | KPI strip, threat levels | T+6:35 | T+7:05 | 30 s |
| 11 | Signals & Intel — Analytics Montage | Event search + change detection | T+7:05 | T+7:55 | 50 s |
| 12 | Cases — Investigation Workflow | Workflow, create case | T+7:55 | T+8:35 | 40 s |
| 13 | Panel Rapid Showcase | Diff, Cameras, Extract, Status, Timeline | T+8:35 | T+9:35 | 60 s |
| 14 | Closing Summary Card | Call to action | T+9:35 | T+10:00 | 25 s |

**Total planned runtime: 10 min 00 sec**

---

## ▶ SCENE 01 — Opening Title Card
**Cumulative: T+0:00 → T+0:20 · 20 seconds**  
**Account: None — pre-production overlay**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SHOW | Black full-screen title card (pre-produced overlay) |
| 2 | +0:00 | CALLOUT | Large text: **ARGUS** |
| 3 | +0:03 | CALLOUT | Subtitle: `Maritime Intelligence Platform` |
| 4 | +0:06 | CALLOUT | Tagline: `Real-Time Multi-Domain Surveillance · Global Coverage` |
| 5 | +0:12 | CALLOUT | Confidentiality notice / production credits fade in |
| 6 | +0:18 | SHOW | Hold — then cinematic fade to dark globe |
| 7 | +0:20 | CUT | → SCENE 02 |

**Narration (Scene 01):**
> *[dramatic pause — no narration until fade completes]*

---

## ▶ SCENE 02 — 3D Globe — Cinematic Open
**Cumulative: T+0:20 → T+1:50 · 90 seconds**  
**Account: Demo mode**  
**Cinematic intent**: Black globe with white coastlines rotates slowly revealing the Persian Gulf. Track trails glow cyan and orange. The analyst zooms to the Strait of Hormuz — the world's most critical maritime chokepoint.

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SHOW | App loads — **3D Globe** is the initial view. CARTO Dark Matter tiles render: jet-black ocean, white coastlines |
| 2 | +0:03 | WAIT | Chokepoint ticker starts scrolling: `HORMUZ HIGH · BAB-EL-MANDEB CRITICAL · SUEZ ELEVATED` |
| 3 | +0:05 | SPEAK | *Begin narration* |
| 4 | +0:08 | DRAG | Slowly rotate globe left → reveal Persian Gulf and Arabian Sea |
| 5 | +0:15 | SCROLL | Zoom in smoothly toward the Strait of Hormuz (lon 56, lat 26.5) |
| 6 | +0:22 | CALLOUT | Highlight: **chokepoint ticker** strip across top — threat levels in color-coded badges |
| 7 | +0:27 | CALLOUT | Highlight: **Intel Briefing** panel overlay on right — executive summary card if visible |
| 8 | +0:33 | CLICK | Sidebar icon **Sensors** (📡) |
| 9 | +0:35 | WAIT | Sensors overlay panel opens |
| 10 | +0:37 | CLICK | Checkbox **Maritime (AIS)** → enable |
| 11 | +0:39 | CLICK | Checkbox **Aviation (ADS-B)** → enable |
| 12 | +0:41 | WAIT | 11 ship track trails (`cyan`) + aircraft tracks (`orange-red`) paint across the globe surface |
| 13 | +0:45 | CALLOUT | Highlight: dense cyan trail cluster in the Strait — inbound and outbound lanes visible |
| 14 | +0:52 | DRAG | Pan slightly to show all 11 vessels spread across the strait waterway |
| 15 | +0:58 | CALLOUT | Highlight: vessel density — tight track separation in the Traffic Separation Scheme |
| 16 | +1:04 | CALLOUT | Highlight: aircraft tracks — scattered over the Gulf, following airways |
| 17 | +1:10 | DRAG | Rotate globe gently — show the curvature of the Earth, the 3D hemisphere view |
| 18 | +1:18 | SCROLL | Zoom out slowly to a mid-globe view — full region context (Iran, UAE, Oman, Arabia) |
| 19 | +1:25 | CALLOUT | Highlight: **2D / 🌐 3D** toggle (top-left map corner) — note it is set to **3D** |
| 20 | +1:30 | CALLOUT | Highlight: map legend (bottom-right) — ship icon in cyan, aircraft icon in orange |
| 21 | +1:38 | CALLOUT | Highlight: **● LIVE** badge in header with UTC timestamp |
| 22 | +1:45 | CUT | → SCENE 03 |

**Narration (Scene 02):**
> *"ARGUS is a real-time, multi-domain intelligence platform built for the world's most critical maritime environments. What you're seeing is a live operational picture of the Strait of Hormuz — twelve miles wide at its narrowest, carrying twenty percent of the world's oil supply through every twenty-four hours. ARGUS fuses satellite imagery, automatic identification system feeds, open-source intelligence, and airspace data into a single, persistent command view. Every vessel you see is tracked. Every gap in their signal is flagged. And every threat assessment updates in real time."*

---

## ▶ SCENE 03 — Animation Playback — Time Warp
**Cumulative: T+1:50 → T+2:50 · 60 seconds**  
**Account: Demo mode**  
**Cinematic intent**: The most dramatic capability in the platform. Thirty hours of maritime activity compress into seconds — vessels fan across the strait in both directions, their trails glowing and fading. The analyst scrubs backward and forward in time.

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SPEAK | *Begin narration* |
| 2 | +0:03 | CALLOUT | Highlight: **▶ / ⏸** play/pause button in main app toolbar |
| 3 | +0:06 | CLICK | **▶** play button |
| 4 | +0:08 | WAIT | Animation begins — trail timestamps advance, ship positions move along their sea-lane routes |
| 5 | +0:12 | CALLOUT | Highlight: glowing cyan trail heads moving along the inbound north lane |
| 6 | +0:18 | CALLOUT | Highlight: outbound south-lane vessels converging toward the Gulf of Oman |
| 7 | +0:24 | CLICK | Speed selector → **4×** |
| 8 | +0:26 | WAIT | Playback accelerates — trails sweep dramatically across the strait |
| 9 | +0:30 | CALLOUT | Highlight: **4×** speed indicator — time-lapse of maritime traffic |
| 10 | +0:36 | CLICK | Speed selector → **1×** — back to real-time rate |
| 11 | +0:39 | CLICK | **⏸** pause button |
| 12 | +0:41 | CALLOUT | Highlight: paused state — entities frozen at a precise historical moment |
| 13 | +0:45 | CALLOUT | Highlight: **↺** reset button — rewinds animation to start of 30-hour window |
| 14 | +0:49 | CLICK | **↺** reset button |
| 15 | +0:51 | WAIT | Animation resets to T+0:00 of window — all tracks return to starting positions |
| 16 | +0:54 | CLICK | **▶** play again |
| 17 | +0:57 | CALLOUT | Highlight: track segments appearing and disappearing — showing historical activity patterns |
| 18 | +1:00 | CUT | → SCENE 04 |

**Narration (Scene 03):**
> *"The ARGUS Replay engine reconstructs any historical time window as a precision intelligence film. Here we're watching thirty hours of strait traffic compressed in real time. Every position report from every vessel, every second of their journey, rendered exactly as it happened. Watch what occurs when we accelerate the clock — four times faster — the traffic separation scheme becomes visible as a pattern, inbound and outbound lanes separating automatically under the maritime rules of the road. ARGUS doesn't just archive data. It lets your analysts replay, pause, and interrogate history — frame by frame."*

---

## ▶ SCENE 04 — Render Modes — Eyes of the Operator
**Cumulative: T+2:50 → T+3:25 · 35 seconds**  
**Account: Demo mode**  
**Cinematic intent**: The globe changes color and character through each render mode — from daylight to night-vision green to thermal orange. A visceral demonstration of multi-spectrum awareness.

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | **⏸** pause animation first |
| 2 | +0:02 | CALLOUT | Highlight: **RenderModeSelector** control (top of map canvas area) |
| 3 | +0:05 | SPEAK | *Begin narration* |
| 4 | +0:07 | CLICK | RenderModeSelector → **LOW LIGHT** |
| 5 | +0:09 | WAIT | Globe shifts to low-ambient-light palette — muted blues and grays |
| 6 | +0:13 | CLICK | RenderModeSelector → **NIGHT VISION** |
| 7 | +0:15 | WAIT | Globe adopts green-tinted night-vision filter — high contrast terrain features |
| 8 | +0:19 | CALLOUT | Highlight: green NV globe — enhanced track visibility against dark background |
| 9 | +0:22 | CLICK | RenderModeSelector → **THERMAL** |
| 10 | +0:24 | WAIT | Thermal palette applies — orange-red heat highlights |
| 11 | +0:27 | CALLOUT | Highlight: THERMAL mode — simulates infrared vessel detection |
| 12 | +0:30 | CLICK | RenderModeSelector → **DAY** |
| 13 | +0:32 | WAIT | Returns to standard day-mode dark globe |
| 14 | +0:34 | CUT | → SCENE 05 |

**Narration (Scene 04):**
> *"ARGUS doesn't operate in a single spectrum. The platform supports four display modes — standard daylight, low-light maritime dusk, night-vision green for twenty-four-hour operations, and thermal overlay for heat-signature analysis. Your operators see what the moment demands — and switch modes instantly."*

---

## ▶ SCENE 05 — Platform Home & Interface Orientation
**Cumulative: T+3:25 → T+3:55 · 30 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SPEAK | *Begin narration* |
| 2 | +0:03 | CALLOUT | Highlight: **ARGUS** logo + animated rings (top-left header) |
| 3 | +0:07 | CALLOUT | Highlight: **● LIVE** badge + UTC clock (header center) |
| 4 | +0:11 | CALLOUT | Highlight: 13 sidebar panel icons (left navigation bar) with labels |
| 5 | +0:16 | CALLOUT | Highlight: **Timeline** slim strip at the very bottom — a row of colored event dots |
| 6 | +0:20 | HOVER | Hover over one event dot on the timeline strip → tooltip shows time + source + count |
| 7 | +0:24 | CALLOUT | Highlight: **2D / 🌐 3D** toggle — emphasis that all panels work in both modes |
| 8 | +0:28 | CUT | → SCENE 06 |

**Narration (Scene 05):**
> *"The ARGUS interface is built around one principle — every piece of intelligence, one screen. The persistent timeline along the bottom tracks every event from every source as colored dots across your entire operational window. Thirteen analysis panels extend from the left rail. Everything stays in sync as you move through time."*

---

## ▶ SCENE 06 — Zones — Define an Area of Interest
**Cumulative: T+3:55 → T+4:35 · 40 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Zones** (⬡) |
| 2 | +0:02 | WAIT | AoiPanel opens — `Strait of Hormuz` AOI already in list |
| 3 | +0:04 | SPEAK | *Begin narration* |
| 4 | +0:07 | CALLOUT | Highlight: **Areas of Interest** panel header + existing AOI entry |
| 5 | +0:11 | CALLOUT | Highlight: **⬜ BBox** and **⬡ Polygon** draw-tool buttons |
| 6 | +0:14 | CLICK | **⬜ BBox** button |
| 7 | +0:16 | WAIT | BBox draw mode activates |
| 8 | +0:18 | DRAG | Draw bounding box on map — cover the Persian Gulf (lon 50–57, lat 23–27) |
| 9 | +0:22 | WAIT | AOI name input appears in panel |
| 10 | +0:24 | TYPE | **AOI name** → `Persian Gulf Monitoring Zone` |
| 11 | +0:28 | CLICK | **Save AOI** button |
| 12 | +0:30 | WAIT | New AOI appears in list — blue rectangle overlay on map |
| 13 | +0:33 | CALLOUT | Highlight: AOI list item — name, delete (✕) button |
| 14 | +0:36 | CALLOUT | Highlight: blue AOI polygon on map — geofence boundary rendered |
| 15 | +0:39 | CUT | → SCENE 07 |

**Narration (Scene 06):**
> *"Analysis begins by defining an area of interest — your operational geofence. Draw a polygon or bounding box on the globe. Name it. Save it. From that moment, every data feed, every detection, every alert is filtered and correlated to that zone automatically. One zone can span twelve miles of a chokepoint or the entire Arabian Sea — ARGUS scales to the mission."*

---

## ▶ SCENE 07 — Dark Ships — AIS Gap Detection
**Cumulative: T+4:35 → T+5:20 · 45 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Dark Ships** (🔦) |
| 2 | +0:02 | WAIT | DarkShipPanel opens — "Running detection…" spinner → candidate list appears |
| 3 | +0:05 | SPEAK | *Begin narration* |
| 4 | +0:08 | CALLOUT | Highlight: panel header with candidate count badge |
| 5 | +0:13 | CALLOUT | Highlight: first row — vessel name and **⚠ SANCTIONED** badge in red |
| 6 | +0:18 | CALLOUT | Highlight: **gap_hours** field — e.g., "48h dark" — duration without AIS signal |
| 7 | +0:22 | CALLOUT | Highlight: **position_jump_km** — suspicious positional leap during dark period |
| 8 | +0:26 | CALLOUT | Highlight: **Confidence** score — ML-derived risk percentage |
| 9 | +0:30 | CALLOUT | Highlight: colored risk dot — CRITICAL (red), HIGH (orange), MEDIUM (amber) |
| 10 | +0:34 | CALLOUT | Highlight: dark gap bar chart per candidate — visual duration indicator |
| 11 | +0:38 | CLICK | First dark ship candidate |
| 12 | +0:40 | WAIT | Map/globe pans to vessel's last known position — animated fly-to |
| 13 | +0:42 | CALLOUT | Highlight: highlighted vessel position marker on map |
| 14 | +0:44 | CUT | → SCENE 08 |

**Narration (Scene 07):**
> *"The Dark Ships module continuously monitors for AIS transmission gaps — the signature of vessels attempting to evade tracking. When a vessel goes dark, ARGUS measures the gap duration, calculates the maximum distance it could have traveled, and cross-references its last registry record against OFAC sanctions lists. The three vessels you're seeing flagged here — including one with a forty-eight-hour transmission gap and a position jump of over four hundred kilometers — are all active detection cases."*

---

## ▶ SCENE 08 — Vessel Profile Modal — Sanctions Screen
**Cumulative: T+5:20 → T+5:55 · 35 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SPEAK | *Begin narration* |
| 2 | +0:03 | CLICK | Vessel name or map marker for sanctioned vessel (from dark ships list) |
| 3 | +0:05 | WAIT | VesselProfileModal opens — modal overlay |
| 4 | +0:08 | CALLOUT | Highlight: vessel flag emoji and vessel name at top |
| 5 | +0:12 | CALLOUT | Highlight: **sanctions-status-badge** — `OFAC-SDN` in deep red |
| 6 | +0:16 | CALLOUT | Highlight: **IMO**, **MMSI**, **Flag**, **Owner**, **Operator** fields |
| 7 | +0:21 | CALLOUT | Highlight: **Last Known Port** and **Gross Tonnage** |
| 8 | +0:25 | CALLOUT | Highlight: **Dark risk** field — colored severity indicator |
| 9 | +0:29 | CALLOUT | Highlight: vessel notes section |
| 10 | +0:32 | CLICK | **✕** modal close button |
| 11 | +0:34 | CUT | → SCENE 09 |

**Narration (Scene 08):**
> *"Every vessel in ARGUS carries a full intelligence profile. One click surfaces IMO registry data, current ownership, flag state, gross tonnage, and — critically — sanctions status cross-referenced against OFAC's SDN list. This vessel is flagged as OFAC-sanctioned, with a forty-eight hour dark gap and a documented position jump consistent with a ship-to-ship transfer. The kind of evidence that supports a compliance brief or a flag-state notification in under sixty seconds."*

---

## ▶ SCENE 09 — Briefing — AI Intelligence Assessment
**Cumulative: T+5:55 → T+6:35 · 40 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Briefing** (🛡) |
| 2 | +0:02 | WAIT | IntelBriefingPanel opens — classification banner + risk level visible |
| 3 | +0:04 | SPEAK | *Begin narration* |
| 4 | +0:07 | CALLOUT | Highlight: **classification banner** at top — "UNCLASSIFIED // DEMO" |
| 5 | +0:12 | CALLOUT | Highlight: **INTELLIGENCE BRIEFING** title + risk level badge (CRITICAL / HIGH) |
| 6 | +0:17 | CALLOUT | Highlight: **executive_summary** paragraph — natural-language AI synthesis |
| 7 | +0:22 | CALLOUT | Highlight: stat pills — **Dark Ships**, **Sanctioned**, **Active** counts |
| 8 | +0:27 | CALLOUT | Highlight: **Key Findings** numbered list — auto-generated from live data |
| 9 | +0:32 | CALLOUT | Highlight: **Vessel Alerts** section — alert type, vessel name, confidence |
| 10 | +0:36 | CLICK | First vessel alert row — cross-links to vessel position on map |
| 11 | +0:38 | WAIT | Map animates to vessel location |
| 12 | +0:39 | CUT | → SCENE 10 |

**Narration (Scene 09):**
> *"This is the ARGUS Intelligence Briefing — a continuously updated commander's summary generated from every active feed. Dark vessel counts. Sanctioned actors. Active anomalies. Key findings translated from raw data into plain language. A new analyst joining an operation gets full situational awareness in under a minute — without touching a filter or writing a query."*

---

## ▶ SCENE 10 — Routes — Chokepoint Monitoring
**Cumulative: T+6:35 → T+7:05 · 30 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Routes** (⚓) |
| 2 | +0:02 | WAIT | ChokepointPanel opens — threat-level cards for each strategic chokepoint |
| 3 | +0:04 | SPEAK | *Begin narration* |
| 4 | +0:07 | CALLOUT | Highlight: first card — name, colored **threat badge** (`CRITICAL`) in red |
| 5 | +0:12 | CALLOUT | Highlight: **MBBL/day** figure — oil flow metric |
| 6 | +0:16 | CALLOUT | Highlight: trend indicator (▲ up) and **vessels / 24h** count |
| 7 | +0:20 | CALLOUT | Highlight: **ChokeMetricsBar** at top — compact KPI strip across all monitored arteries |
| 8 | +0:24 | CLICK | `Strait of Hormuz` chokepoint card |
| 9 | +0:26 | WAIT | Map flies to chokepoint — location highlighted |
| 10 | +0:29 | CUT | → SCENE 11 |

**Narration (Scene 10):**
> *"The Routes module monitors the world's strategic maritime chokepoints in real time. Current threat level — CRITICAL at Hormuz. Seventeen million barrels of oil flow through daily. Vessel count trending upward. These are the five maritime arteries that move forty percent of global seaborne trade — and ARGUS watches all of them simultaneously."*

---

## ▶ SCENE 11 — Signals & Intel — Analytics Montage
**Cumulative: T+7:05 → T+7:55 · 50 seconds**  
**Account: Demo mode**  
**Cinematic intent**: Two panels shown in rapid succession — demonstrate depth without slowing the narrative.

### Part A: Signals (25 seconds)

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Signals** (⚡) |
| 2 | +0:02 | WAIT | SearchPanel opens |
| 3 | +0:04 | SPEAK | *Begin narration — Signals* |
| 4 | +0:07 | CLICK | **Search** button |
| 5 | +0:09 | WAIT | Event list: colored source badges per event |
| 6 | +0:12 | CALLOUT | Highlight: badge types — `aisstream`, `gdelt`, `opensky`, `acled`, `sentinel2` |
| 7 | +0:16 | CALLOUT | Highlight: `confidence` percentage per event |
| 8 | +0:20 | CLICK | First event in list |
| 9 | +0:22 | WAIT | Corresponding marker highlights on globe |
| 10 | +0:24 | CUT | → Part B |

**Narration (Part A):**
> *"Signals aggregates every raw intelligence event from every connected source into a single searchable stream — AIS, airspace, open-source media, and ACLED conflict data — each tagged with a machine-confidence score."*

### Part B: Intel / Change Detection (25 seconds)

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 11 | +0:25 | CLICK | Sidebar icon **Intel** (◈) |
| 12 | +0:27 | WAIT | AnalyticsPanel opens |
| 13 | +0:29 | SPEAK | *Begin narration — Intel* |
| 14 | +0:31 | CLICK | **Run Change Detection** button |
| 15 | +0:33 | WAIT | `Running…` → candidate list populates (3–10 items) |
| 16 | +0:37 | CALLOUT | Highlight: first change — **change_class** label (e.g., `vessel_construction`) |
| 17 | +0:41 | CALLOUT | Highlight: **rationale** paragraph — AI natural-language explanation |
| 18 | +0:44 | CLICK | **✓ Confirm** on first candidate |
| 19 | +0:46 | WAIT | Badge turns green — `confirmed` |
| 20 | +0:49 | CUT | → SCENE 12 |

**Narration (Part B):**
> *"The Intel module runs automated change detection across multi-temporal satellite imagery — detecting construction, vessel movements, and infrastructure changes. Each detection carries an AI-generated rationale. Analysts confirm or dismiss with a single click — creating an auditable intelligence record."*

---

## ▶ SCENE 12 — Cases — Investigation Workflow
**Cumulative: T+7:55 → T+8:35 · 40 seconds**  
**Account: Demo mode**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | CLICK | Sidebar icon **Cases** (🔍) |
| 2 | +0:02 | WAIT | InvestigationsPanel opens — list with status badges |
| 3 | +0:04 | SPEAK | *Begin narration* |
| 4 | +0:07 | CALLOUT | Highlight: `Case-001 Dark Vessel Cluster` — **active** status (green) |
| 5 | +0:11 | CLICK | **+ New** button |
| 6 | +0:13 | WAIT | Create-case form expands |
| 7 | +0:15 | TYPE | **Case Name** → `Op-042 Sanctions Evasion Monitor` |
| 8 | +0:19 | TYPE | **Description** → `Monitoring potential petroleum transfer near Kish Island` |
| 9 | +0:25 | TYPE | **Tags** → `petroleum, sanctions, shadow-fleet` |
| 10 | +0:29 | CLICK | **Create** button |
| 11 | +0:31 | WAIT | New investigation appears with **draft** badge |
| 12 | +0:33 | CLICK | `Case-001 Dark Vessel Cluster` to expand |
| 13 | +0:35 | CALLOUT | Highlight: **Absence Signals** — AIS Gap, GPS Denial severity indicators |
| 14 | +0:38 | CALLOUT | Highlight: CRITICAL (red), HIGH (orange) color coding |
| 15 | +0:40 | CUT | → SCENE 13 |

**Narration (Scene 12):**
> *"Every detection, every dark ship, every confirmed change feeds into the Cases module — a structured investigation workflow designed for the full analyst lifecycle. Cases are traceable, shareable, and exportable. From the moment an anomaly is detected to the moment a brief reaches a decision-maker, every action is logged."*

---

## ▶ SCENE 13 — Panel Rapid Showcase
**Cumulative: T+8:35 → T+9:35 · 60 seconds**  
**Account: Demo mode**  
**Cinematic intent**: A brisk montage — five panels in sixty seconds. Each gets one strong callout. Sets the breadth of the platform without slowing pace.

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| **Diff — Imagery Compare** | | | |
| 1 | +0:00 | CLICK | Sidebar icon **Diff** (⊟) |
| 2 | +0:02 | WAIT | ImageryComparePanel opens — BEFORE / AFTER card layout |
| 3 | +0:04 | SPEAK | *Begin Diff narration* |
| 4 | +0:06 | CALLOUT | Highlight: **BEFORE** (amber left-border) and **AFTER** (blue left-border) scene cards |
| 5 | +0:10 | CALLOUT | Highlight: cloud cover %, date, provider, days gap between acquisitions |
| 6 | +0:13 | CUT | → Cameras |
| **Cameras — Sensor Feed** | | | |
| 7 | +0:14 | CLICK | Sidebar icon **Cameras** (📷) |
| 8 | +0:16 | WAIT | CameraFeedPanel opens — camera list with type badges |
| 9 | +0:18 | CALLOUT | Highlight: type badges — **OPT**, **THM**, **NV**, **SAR** |
| 10 | +0:22 | CALLOUT | Highlight: **●LIVE** badge on active feeds |
| 11 | +0:25 | CUT | → Timeline |
| **Timeline — Slim Event Strip** | | | |
| 12 | +0:26 | SHOW | Scroll to bottom of screen — Timeline slim strip visible |
| 13 | +0:28 | CALLOUT | Highlight: colored event dots along the timeline track |
| 14 | +0:30 | HOVER | Hover dot → tooltip: source name + count |
| 15 | +0:33 | CLICK | **▲** expand button on timeline |
| 16 | +0:35 | WAIT | Expands to 120px — shows preset buttons (**24h / 7d / 30d**) + bar chart histogram |
| 17 | +0:38 | CLICK | **30d** preset |
| 18 | +0:40 | WAIT | Chart expands to 30-day window |
| 19 | +0:42 | CLICK | **▲** collapse button |
| 20 | +0:44 | CUT | → Extract |
| **Extract — Export Job** | | | |
| 21 | +0:45 | CLICK | Sidebar icon **Extract** (↓) |
| 22 | +0:47 | WAIT | ExportPanel opens |
| 23 | +0:48 | CALLOUT | Highlight: format options — **CSV** and **GeoJSON** |
| 24 | +0:50 | CLICK | Format → `GeoJSON` → **Export** button |
| 25 | +0:52 | WAIT | `Done — N rows` status |
| 26 | +0:54 | CUT | → Status |
| **Status — System Health** | | | |
| 27 | +0:55 | CLICK | Sidebar icon **Status** (◉) |
| 28 | +0:57 | WAIT | SystemHealthPage loads |
| 29 | +0:58 | CALLOUT | Highlight: green **OK** banner — Infrastructure, Satellite Providers, Data Connectors |
| 30 | +1:00 | CUT | → SCENE 14 |

**Narration (Scene 13):**
> *"Diff places any two satellite acquisitions side by side — measuring days, cloud cover, and the delta between them. Cameras aggregates every registered sensor feed — optical, thermal, night-vision, SAR — all time-synced to the live playback clock. The Timeline strip at the bottom anchors every event across every source in a single visual timeline. Extract exports any dataset in open formats — GeoJSON or CSV — in seconds. And Status gives operators a live health check on every infrastructure component, every provider, every data connector."*

---

## ▶ SCENE 14 — Closing Summary Card
**Cumulative: T+9:35 → T+10:00 · 25 seconds**  
**Account: None — post-production overlay**

| Step | T+ | Type | Target → Value |
|------|----|------|-----------------|
| 1 | +0:00 | SHOW | Fade to black from the live app |
| 2 | +0:02 | SHOW | Closing overlay card (dark background, matching opening) |
| 3 | +0:03 | SPEAK | *Begin narration* |
| 4 | +0:03 | CALLOUT | Text: **ARGUS** — large |
| 5 | +0:06 | CALLOUT | Capability matrix — checklist of all 13 modules in two columns |
| 6 | +0:12 | CALLOUT | `Real-Time Maritime Intelligence · Sentinel-2 · Landsat · AIS · ADS-B · GDELT` |
| 7 | +0:17 | CALLOUT | Contact / next-steps CTA for customer or investor |
| 8 | +0:23 | SHOW | Fade to black |
| 9 | +0:25 | END | |

**Narration (Scene 14):**
> *"ARGUS — persistent, multi-domain intelligence at global scale. Thirteen integrated modules. Eleven live data connectors. Real-time and historical analysis in one operational picture."*

---

## APPENDIX A — Screen Inventory

| # | Screen / Panel | Path / Trigger | Panel Key |
|---|---------------|----------------|-----------|
| 1 | Application Home | `http://localhost:5173` | — |
| 2 | 3D Globe View | **🌐 3D** toggle (top-left map canvas) | `viewMode=3d` |
| 3 | 2D Map View | **2D** toggle (top-left map canvas) | `viewMode=2d` |
| 4 | Zones — Areas of Interest | Sidebar → ⬡ Zones | `aoi` |
| 5 | Zones — Draw BBox tool | AoiPanel → ⬜ BBox button | `aoi` |
| 6 | Zones — Draw Polygon tool | AoiPanel → ⬡ Polygon button | `aoi` |
| 7 | Zones — Save AOI form | After drawing geometry | `aoi` |
| 8 | Sensors — Layer Panel | Sidebar → 📡 Sensors | `layers` |
| 9 | Timeline — Slim Event Strip | Fixed bottom bar (always visible) | — |
| 10 | Timeline — Expanded Histogram | Click **▲** on timeline strip | — |
| 11 | Signals — Event Search | Sidebar → ⚡ Signals | `search` |
| 12 | Replay — Playback | Sidebar → ▶ Replay (or top toolbar ▶/⏸ buttons) | `playback` |
| 13 | Intel — Change Detection | Sidebar → ◈ Intel | `analytics` |
| 14 | Routes — Chokepoints | Sidebar → ⚓ Routes | `chokepoints` |
| 15 | Dark Ships — AIS Gaps | Sidebar → 🔦 Dark Ships | `darkships` |
| 16 | Briefing — Intel Summary | Sidebar → 🛡 Briefing | `intelbrief` |
| 17 | Extract — Export Panel | Sidebar → ↓ Extract | `export` |
| 18 | Diff — Imagery Compare | Sidebar → ⊟ Diff | `compare` |
| 19 | Cameras — Sensor Feed | Sidebar → 📷 Cameras | `cameras` |
| 20 | Status — System Health | Sidebar → ◉ Status | `health` |
| 21 | Cases — Investigations | Sidebar → 🔍 Cases | `investigations` |
| 22 | Vessel Profile Modal | Click vessel on map or in alert/dark-ships list | popup |
| 23 | RenderModeSelector | Top of map canvas — DAY / LOW LIGHT / NIGHT VISION / THERMAL | — |
| 24 | Opening Title Card | Pre-production overlay | — |
| 25 | Closing Summary Card | Post-production overlay | — |

---

## APPENDIX B — Narration Word Count & Timing

| Scene | Word Count | Est. Duration | Allowed Duration |
|-------|-----------|---------------|-----------------|
| 01 | 0 | 0 s | 20 s |
| 02 | ~165 | 76 s | 90 s |
| 03 | ~135 | 62 s | 60 s |
| 04 | ~65 | 30 s | 35 s |
| 05 | ~65 | 30 s | 30 s |
| 06 | ~80 | 37 s | 40 s |
| 07 | ~120 | 55 s | 45 s |
| 08 | ~105 | 48 s | 35 s |
| 09 | ~85 | 39 s | 40 s |
| 10 | ~60 | 28 s | 30 s |
| 11A | ~50 | 23 s | 25 s |
| 11B | ~65 | 30 s | 25 s |
| 12 | ~70 | 32 s | 40 s |
| 13 | ~110 | 51 s | 60 s |
| 14 | ~35 | 16 s | 25 s |

> **Note**: Scenes 07 and 08 narration runs slightly long — either trim delivery pace or compress the callout steps to stay within the allocated window.

---

## APPENDIX C — Key Callout Points for Recording Editor

The following are the most visually impressive moments to emphasize with zoom-in / highlight overlays in post-production:

1. **T+0:20 — Dark Globe First Reveal** — The CARTO dark tile sphere coming into view against a black background; white coastline geometry. Zoom-in post-effect recommended.
2. **T+0:45 — Track Trails on Globe** — The moment 11 cyan ship trails + orange aircraft tracks light up on the globe surface. Full-color saturation boost in post.
3. **T+1:50 — Animation Start** — First frame of vessels moving in real-time along sea lanes. Consider slow-motion ramp then full-speed transition.
4. **T+2:24 — 4× Speed Acceleration** — Tracks sweeping rapidly across the screen. High-energy moment.
5. **T+2:57 — Night Vision Mode** — Green globe with tracks. Strong visual identity moment.
6. **T+3:07 — Thermal Mode** — Orange-red palette. Visceral.
7. **T+5:12 — SANCTIONED Badge** — Red `OFAC-SDN` badge in the dark ship list. Hold on this for 1–2 extra seconds.
8. **T+6:17 — Executive Briefing** — AI-generated summary paragraph. Pan down slowly through the text.

---

## APPENDIX D — Troubleshooting Reference

| Problem | Fix |
|---------|-----|
| Globe tiles show a colorful daytime map instead of dark | Hard-refresh browser (Ctrl+Shift+R). CARTO Dark Matter tiles must load from CDN. |
| Ship tracks not visible | Ensure **Maritime (AIS)** checkbox is enabled in Sensors panel. |
| Tracks appear to jump or stutter | Resize animation window — ensure `window_h = 30` in `src/services/demo_seeder.py` and backend was restarted after the change. |
| Timeline panel occupies full bottom area (old version) | Hard-refresh browser. New slim-bar version is in `frontend/src/components/TimelinePanel/TimelinePanel.tsx`. Ensure `pnpm build` was re-run. |
| Animation playback controls not visible | The ▶ / ⏸ / ↺ buttons are in the main app toolbar (App.tsx) — not inside the Replay sidebar panel. Look at the top of the viewport. |
| Render mode selector missing | Located at the top of the map canvas area — labeled DAY / LOW LIGHT / NIGHT VISION / THERMAL. |
| Backend 500 on `/api/v1/playback/query` | Confirm backend running with `APP_MODE=demo` in `.env` |
| Dark ships list empty | Navigate first to the Dark Ships panel — it auto-triggers detection on panel open. Allow 2–3 seconds for the list to populate. |
