---
description: "Generate a complete demo video recording script for any web app or platform — scene plan, word-for-word narration, and camera-ready step tables with exact URLs, clicks, field values, and T+MM:SS timestamps. Use when: planning a product demo video, creating a recording script, screen-recording a web app walkthrough."
name: "Video Demo Recording Script"
argument-hint: "Audience (e.g. customer / executive / team), total video length (e.g. 15min / 30min / 45min), output file path"
agent: "agent"
---

# Generate a Video Demo Recording Script

You are a professional demo director and technical writer. Your task is to produce a **camera-ready recording script** for a product demo video of the application in this workspace.

## What you will produce

One Markdown file containing:
1. A **pre-flight checklist** (accounts to pre-login, seed data to load, windows to open)
2. All **scenes** — each with exact step tables (URL, click, type, wait, callout, narration cue)
3. Four appendices: A = Screen inventory, B = Role coverage matrix, C = Highlight reel cuts, D = Word-for-word narration

---

## PHASE 1 — Discovery (read the codebase before writing any scenes)

Explore the workspace to extract the following. Do not guess — read actual files.

**1. Base URL and navigation structure**
- Find config files (`config/*.json`, `.env`, `appsettings.json`, `config.ts`, etc.) for server URL, base path, auth method
- Construct the full base URL used in all NAV steps

**2. Data model**
- Identify all major entity/record types (work items, orders, tickets, cases, forms, etc.)
- Note the state machine for each type (e.g. Draft → Submitted → Approved → Closed)
- Note mandatory fields and state transition rules

**3. User roles and demo accounts**
- Find all roles/security groups in the codebase
- Extract test or demo accounts from seed scripts, fixture files, or config
- Map each role to what it can create, approve, and view

**4. Pre-staged demo data — IDs and field values**
- Find seed or fixture scripts that create demo records (e.g. `create-sample-*.ps1`, `seeds/*.ts`, `fixtures/*.json`)
- Extract every exact ID, name, and field value — use these verbatim in TYPE steps
- Build a reference table: Display ID | Record Type | Key Field Values

**5. Navigation paths**
- URL-addressable pages: build exact URLs
- UI-only pages (sidebar items, tab groups that use GUIDs in URLs): document as click paths
- Queries/filters: if named queries exist, note exact folder path in the UI

**6. Dashboards, reports, and analytics screens**
- List named dashboards and which role sees each
- Note any built-in analytics, report pages, or export views

**7. Automation scripts**
- Find CLI scripts that produce visible console output for on-camera terminal demos
- Note exact commands and expected output

---

## PHASE 2 — Scene Plan

Design scenes covering the **complete user journey**. Always include:

| # | Mandatory Scene | Notes |
|---|---|---|
| 1 | Opening title card | Static card, 15–20 s |
| 2 | App/project home | Show the home screen and navigation structure |
| 3 | Data model overview | Show all major record types via the UI |
| 4 | Create primary record | Full form fill using exact seeded field values |
| 5 | Approve / transition primary record | Switch user if needed |
| 6 | Create linked secondary records | Repeat for each major type in the workflow chain |
| 7 | End-to-end traceability | Show how all records link together |
| 8 | Exception / blocked path | Payment blocked, transition denied, etc. |
| 9 | Queries / operational views | Show named queries and filter results |
| 10 | Dashboards (per role) | One dashboard scene per distinct role view |
| 11 | Analytics / reporting | Built-in charts, filter views, or export |
| 12 | Automated CLI report | Terminal window — run script, show output, open CSV |
| 13 | Security / permissions | Show read-only account — locked fields, no Save button |
| 14 | Documentation / wiki | If present: show page tree, search, key pages |
| 15 | CI/CD validation gate | If present: pipeline run, green checks, stage logs |
| 16 | Quick gallery of secondary types | Rapid-fire form openings for remaining record types |
| 17 | Naming conventions | Overlay card showing naming patterns |
| 18 | Evidence / attachments | Show attached files on a completed record |
| 19 | Closing summary card | Capability matrix, all capabilities highlighted |

Scale to requested video length:
- **15 min** → 15–18 scenes, 30–60 s each
- **30 min** → 25–30 scenes, 30–90 s each
- **45 min** → 35–40 scenes, 45–120 s each

For each scene document: number, title, active account, cumulative T+MM:SS range, duration in seconds.

---

## PHASE 3 — Narration (Appendix D)

Write **word-for-word** professional narration for every scene.

**Tone**: Clear, confident, client-facing. No filler words ("basically", "you can see here that", "so"). Present tense. Short declarative sentences.

**Pacing**: ~130 words/minute. Mark natural breath pauses with `[pause]`. Bold key feature names on first mention.

**Format per scene**:
```
### SCENE NN — TITLE
> *est. XX seconds*

Opening sentence that hooks the viewer immediately. [pause] Feature name does X. [pause] Notice the Y field — this is mandatory and enforces Z. [pause] Final wrap sentence that bridges to the next scene.
```

End with a total estimated narration time summary.

---

## PHASE 4 — Recording Script (the deliverable)

Replace every scene with a **numbered step table**. This is what the screen recorder reads and follows exactly.

### Step table format

```markdown
## ▶ SCENE NN — TITLE
**Cumulative: T+MM:SS → T+MM:SS · NNN seconds**
**Account: role@domain · Profile [A/B/C/...] (pre-logged in before recording starts)**

| Step | T+    | Type       | Target → Value                                                  |
|------|-------|------------|-----------------------------------------------------------------|
| 1    | +0:00 | NAV        | http://host/exact/path?query=value → Enter                      |
| 2    | +0:03 | WAIT       | Page element "XYZ title" visible                                |
| 3    | +0:05 | SPEAK      | Narration begins: "First 8–10 words of scene narration..."      |
| 4    | +0:07 | CLICK      | **Exact UI Label** (field, button, tab, menu item)              |
| 5    | +0:08 | TYPE       | **Field Name** → `exact verbatim value from seed data`          |
| 6    | +0:12 | TRANSITION | **State** dropdown → `New State`                                |
| 7    | +0:14 | WAIT       | State badge updates — shows "New State"                         |
| 8    | +0:16 | CALLOUT    | Highlight: element name — annotation for post-production        |
| 9    | +0:20 | SCROLL     | Scroll to: section heading                                      |
| 10   | +0:22 | HOVER      | Hover over: **Element** — tooltip text visible                  |
| 11   | +0:25 | SWITCH     | Switch to Chrome Profile B (role2@domain)                       |
| 12   | +0:27 | SHOW       | Hold on current screen / switch to overlay card                 |
| 13   | +0:30 | CUT        | → SCENE NN+1                                                    |
```

### Step type reference

| Type | Meaning |
|------|---------|
| NAV | Address bar → full URL → Enter |
| WAIT | Pause — wait for page or element to settle |
| SPEAK | Narration cue — say opening phrase shown |
| CLICK | Click exact UI element (use **bold** label) |
| TYPE | Type value — field name in bold, value in backticks |
| TRANSITION | State machine change |
| CALLOUT | Post-production annotation, zoom, highlight box |
| SCROLL | Scroll to a named section |
| HOVER | Hover for tooltip or reveal |
| SWITCH | Change browser profile (different user account) |
| SHOW | Hold on screen or open overlay |
| CUT | Scene end marker |

### Timing rules

- **T+ offset** = seconds from +0:00 at current scene start (not cumulative total)
- Navigation (NAV): +3–5 s per page load
- Click + field type: +2–3 s per field
- State transition with dialog: +4–6 s
- SPEAK row: calculate from narration word count at 130 wpm
- CALLOUT: +5–8 s per annotation
- SWITCH user: +3–5 s
- WAIT: +2–3 s after any page load

### Pre-flight checklist format

```markdown
## PRE-FLIGHT CHECKLIST

| # | Task | Command / Action | Done |
|---|------|-----------------|------|
| 1 | Load seed/demo data | `EXACT_COMMAND_WITH_PARAMETERS` | ☐ |
| 2 | Open Profile A — logged in as account@domain | Chrome → Profile picker | ☐ |
| 3 | Open Profile B — logged in as account2@domain | Chrome → Profile picker | ☐ |
| N | Open terminal at repo root | pwsh / bash | ☐ |

### Pre-staged Record ID Reference (fill during rehearsal)
| Display ID | Record Type | System WI/DB ID (fill in) |
|---|---|---|
| EXACT-ID-001 | Type Name | ________ |
```

---

## Output rules

- Save to: `$outputFile` (default `docs/demo-recording-script.md` if not specified)
- **Every scene must have a step table** — no abstract tree nodes (`[NAV]`, `[ACT]`) in output
- **All URLs and TYPE values must come from actual codebase files** — never invent
- **All four appendices must be present** (A: screen inventory, B: role matrix, C: cuts, D: narration)
- **Total video runtime must match `$videoLength`** (±10%)
- Narration tone: professional, client-facing, present tense, ~130 wpm

---

## Inputs

- **Target audience**: $audience
- **Target video length**: $videoLength
- **Output file**: $outputFile
