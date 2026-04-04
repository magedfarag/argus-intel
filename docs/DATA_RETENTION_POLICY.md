# Data Handling and Retention Policy

**Document type:** Governance  
**Phase:** 6 Track A  
**Status:** Active (in-memory stores — automated purge is Phase 6+ work)  
**Last updated:** 2026-04-04

---

## 1. Scope

This policy applies to all data flowing through the ARGUS platform, including raw
payloads ingested from external data sources and normalised canonical events stored by
the unified data plane.

---

## 2. Retention Durations by Source Family

| Source Family | Raw Payload | Normalised Event | Notes |
|---------------|-------------|------------------|-------|
| **AIS (maritime)** | 30 days | 1 year | Raw includes full vessel position records (NMEA/JSON blobs) |
| **OpenSky (aviation)** | 7 days | 90 days | Non-commercial reuse; see licence constraints below |
| **GDELT (news/events)** | 7 days | Not retained (ephemeral) | Contextual enrichment only; no long-term normalised store |
| **Imagery references** | N/A (external URLs) | 90 days (metadata only) | Scene metadata, thumbnails, and bounding boxes; actual raster data is not stored |
| **Investigations** | N/A | Indefinite | User-generated content; not subject to automated purge |
| **Audit logs** | — | 1 year minimum | Append-only; must not be modified or truncated before 1-year mark |
| **Canonical events (generic)** | 30 days raw | 90 days normalised | Default for source families not listed above |

---

## 3. Raw vs Normalised Retention

**Raw payload** refers to the verbatim bytes received from an upstream source API
(e.g. an AIS NMEA sentence, an OpenSky JSON state vector, a GDELT article record).
Raw payloads are stored to support:
- Replay-safe re-ingestion if the normalisation pipeline is updated.
- Provenance audits and licence compliance checks.

**Normalised event** refers to a record that has been mapped to the canonical event
schema (`CanonicalEvent`) and stored in the unified event store.  Normalised events
are the primary operational dataset used by all query and playback APIs.

Raw payloads have shorter retention periods because they consume more storage and may
contain third-party data with licence-restricted re-distribution windows.  Normalised
events may be retained longer because they carry no raw third-party bytes.

---

## 4. Third-Party Licence Constraints

| Source | Licence | Constraint |
|--------|---------|------------|
| **AIS (commercial via AISStream / RapidAPI)** | Commercial subscription | Raw payloads may not be redistributed or retained beyond the subscription agreement's data handling addendum.  Default: 30 days. |
| **OpenSky Network** | Creative Commons BY-NC-SA 4.0 | Non-commercial use only.  Attribution required.  Derived products (normalised events) may be retained for research/operational non-commercial purposes. |
| **GDELT 2.0** | Creative Commons CC0 (public domain) | No attribution required; no redistribution restriction.  Retained only 7 days to limit storage costs. |
| **Sentinel-2 (ESA Copernicus)** | Copernicus Open Access (CC BY 4.0) | Free for commercial and non-commercial use with attribution.  Only scene metadata is stored; full raster tiles are not persisted. |
| **Landsat (USGS)** | Public domain (US government) | No redistribution restriction. |
| **Maxar SecureWatch** | Commercial licence required | Imagery tiles must not be cached beyond the licence agreement's retention window.  Platform currently stores no Maxar raster data. |
| **Planet PlanetScope / SkySat** | Commercial licence required | Same as Maxar — no raw tile persistence. |

---

## 5. Current Implementation Status

> **Important:** The current platform uses **in-memory stores** for all event,
> investigation, and signal data.  There is no automated purge mechanism.  Data
> persists only for the lifetime of the server process.

Implications:
- Retention durations above describe the **policy target**, not the current
  enforcement state.
- When a durable storage layer is introduced (PostgreSQL, object storage), a
  background job must enforce TTL-based deletion according to this policy.
- Audit logs are emitted to the Python logging system (`argus.audit`); persistence
  beyond the process lifetime requires log aggregation (e.g. shipping to an
  append-only store such as S3, Elasticsearch, or a SIEM).

Migration to durable storage with automated TTL enforcement is tracked as a
**Phase 6+** task.

---

## 6. Data Subject Rights (Preliminary)

The platform currently stores no personally identifiable information (PII) from
end-users.  Operator-assigned entity labels (vessel names, ICAO callsigns) are
treated as operational metadata, not personal data.

If the platform is extended to process personal data, a Data Protection Impact
Assessment (DPIA) must be completed before deployment.

---

## 7. Audit Log Integrity

Audit log entries are append-only and must not be:
- Modified retroactively.
- Deleted before the 1-year minimum retention period has elapsed.
- Truncated for any reason other than a documented, authorised data lifecycle event.

Each audit record contains a hashed `user_id` (SHA-256 prefix, 16 hex chars) rather
than the raw identifier, providing attribution traceability without storing cleartext
credentials.

---

## 8. Review Cadence

This policy should be reviewed:
- When a new source family is onboarded.
- When the platform is promoted to a production deployment.
- At minimum annually.
