# ARGUS — Disaster Recovery

**Version:** 1.0  
**Phase:** 6 Track C  
**Last updated:** 2026-04-04

---

## 1. Data Architecture and Durability Summary

ARGUS operates an in-memory-first architecture in its demo and staging
profiles.  This section documents what is durable, what is ephemeral, and the
exact implications of a service crash or restart.

### 1.1 In-Memory State (Ephemeral — Lost on Restart)

| Store | Contents | Durability |
|---|---|---|
| `EventStore` | Ingested CanonicalEvents (AIS, OpenSky, GDELT, imagery) | **None** — lost on process restart |
| `AoiStore` | Area-of-Interest geometries and metadata | **None** — lost on restart |
| `InvestigationStore` | Saved investigation objects, notes, watchlist | **None** — lost on restart |
| `TelemetryStore` | Ship and aircraft position tracks | **None** — lost on restart |
| `SourceHealthService` | Connector health records and freshness state | **None** — rebuilt from first probe cycle |

> **Known limitation:** The in-memory store pattern is an intentional demo
> trade-off.  The path to durable storage is documented in §5.

### 1.2 Durable Artifacts

| Artifact | Storage Location | Durability |
|---|---|---|
| Evidence pack exports (JSON) | Object storage (`OBJECT_STORAGE_BUCKET/evidence-packs/`) | Durable — survives restart |
| Evidence pack exports (Parquet) | Object storage (`OBJECT_STORAGE_BUCKET/exports/`) | Durable — survives restart |
| Audit log files | Object storage (`OBJECT_STORAGE_BUCKET/audit/`) | Durable — append-only |
| Database job history | PostgreSQL (`DATABASE_URL`) when configured | Durable — survives restart |
| Alembic migrations | Filesystem (`alembic/versions/`) | Durable — version-controlled |
| Container images | Docker registry / local `docker images` | Durable — tagged releases |

When `OBJECT_STORAGE_ENDPOINT` is not configured, exports are written to the
local filesystem under `/tmp/argus-exports/` which is **not** durable across
container rebuilds.

---

## 2. Recovery Point Objective (RPO)

RPO is the maximum acceptable data age at the moment of recovery.

| Deployment Profile | RPO | Rationale |
|---|---|---|
| **Demo** (in-memory only) | Unlimited — all event data is lost on restart | No persistence layer; acceptable for demo use |
| **Staging** (in-memory + object storage exports) | Time of last manual export | Evidence packs and Parquet exports are durable; raw events are not |
| **Production** (Postgres + Redis) | < 5 minutes | Postgres persists all events; Celery queue preserves unprocessed tasks in Redis |

---

## 3. Recovery Time Objective (RTO)

RTO is the maximum time to restore the service to an operational state.

| Deployment Profile | RTO | Recovery Mechanism |
|---|---|---|
| **Demo** | < 2 minutes | `docker compose up -d`; demo seeder re-seeds synthetic data automatically |
| **Staging** | < 5 minutes | Restart containers; manually re-import exported evidence packs if needed |
| **Production** | < 10 minutes | Blue/green container swap; Alembic migrations pre-run on deploy |

---

## 4. Backup and Restore Procedures

### 4.1 Evidence Pack Backup

Evidence packs are written to object storage at export time.  They contain the
full event payload required to reconstruct an investigation.

```bash
# List all evidence packs in object storage
aws s3 ls s3://${OBJECT_STORAGE_BUCKET}/evidence-packs/ \
  --endpoint-url ${OBJECT_STORAGE_ENDPOINT}

# Download all evidence packs locally
aws s3 sync s3://${OBJECT_STORAGE_BUCKET}/evidence-packs/ ./backup/evidence-packs/ \
  --endpoint-url ${OBJECT_STORAGE_ENDPOINT}
```

### 4.2 Investigation Export and Restore

Export investigations before any planned restart:

```bash
# Export all active investigations
mkdir -p ./backup/investigations
for id in $(curl -s http://localhost:8000/api/v1/investigations \
    | python -c "import sys,json; [print(i['id']) for i in json.load(sys.stdin)['items']]"); do
  curl -s http://localhost:8000/api/v1/investigations/$id/export \
    > ./backup/investigations/inv_$id.json
  echo "Exported investigation $id"
done
```

Restore by POSTing each JSON file back to the create endpoint after restart:

```bash
for f in ./backup/investigations/*.json; do
  curl -s -X POST http://localhost:8000/api/v1/investigations \
    -H "Content-Type: application/json" \
    -d @$f
done
```

### 4.3 Event Data Parquet Export and Restore

```bash
# Export all events to Parquet before a disruptive operation
curl -s -X POST http://localhost:8000/api/v1/export/events \
  -H "Content-Type: application/json" \
  -d '{
    "format": "parquet",
    "start_time": "2020-01-01T00:00:00Z",
    "end_time": "2099-01-01T00:00:00Z"
  }' -o ./backup/events_$(date +%Y%m%d_%H%M%S).parquet
```

Restore is currently a manual re-ingest operation; no bulk ingest endpoint
exists in the demo profile.  For production, raw payloads in object storage
can be replayed through the connector pipeline.

### 4.4 PostgreSQL Backup (Production)

```bash
# Full logical backup
pg_dump $DATABASE_URL \
  --format=custom \
  --compress=9 \
  --file=argus_$(date +%Y%m%d_%H%M%S).dump

# Restore
pg_restore --clean --if-exists -d $DATABASE_URL argus_<timestamp>.dump
```

Set up a daily cron job or managed backup schedule (AWS RDS automated snapshots,
Cloud SQL, etc.) with a minimum 7-day retention.

### 4.5 Audit Log Backup

Audit logs are append-only in object storage.  Back them up by syncing to a
secondary bucket or offline storage:

```bash
aws s3 sync s3://${OBJECT_STORAGE_BUCKET}/audit/ \
  s3://${AUDIT_BACKUP_BUCKET}/audit/ \
  --endpoint-url ${OBJECT_STORAGE_ENDPOINT}
```

---

## 5. Path to Durable Storage (Upgrade Guide)

The following steps migrate ARGUS from the in-memory demo architecture to a
fully durable production deployment:

### Step 1 — PostgreSQL for Event Persistence

1. Set `DATABASE_URL` in `.env` to a PostgreSQL connection string.
2. Run `alembic upgrade head` to create the schema.
3. Update `EventStore`, `AoiStore`, and `InvestigationStore` to write through to
   Postgres (see `docs/ARCHITECTURE.md` — "Persistence Layer" section).
4. RPO drops to < 5 minutes; RTO drops to < 10 minutes.

### Step 2 — Redis for Queue Durability

1. Set `REDIS_URL` in `.env`.
2. Celery tasks are now persisted in Redis; unprocessed work survives worker
   restarts.
3. `CacheClient` uses Redis-backed LRU cache instead of the in-process
   `cachetools` fallback.

### Step 3 — Object Storage for Raw Payloads

1. Set `OBJECT_STORAGE_ENDPOINT`, `OBJECT_STORAGE_ACCESS_KEY`,
   `OBJECT_STORAGE_SECRET_KEY`, and `OBJECT_STORAGE_BUCKET`.
2. Connectors optionally write raw API responses to `raw/<source>/<date>/` before
   normalisation, enabling full replay without re-hitting upstream APIs.

### Step 4 — Scheduled Backups

1. Enable `pg_dump` cron job or cloud-managed snapshots.
2. Configure S3 cross-region replication for the object storage bucket.
3. Test restore procedure quarterly.

---

## 6. Emergency Contacts and Escalation

| Scenario | First contact | Escalate to |
|---|---|---|
| Complete service outage | On-call engineer (PagerDuty) | Platform lead |
| Data loss (unintentional) | On-call engineer | Security + Legal |
| Audit log loss | Security team | CISO |
| Credential compromise | Security team | Incident Command |

See `docs/ONCALL.md` for on-call rotation details and contact information.

---

## 7. DR Test Schedule

| Test | Frequency | Owner |
|---|---|---|
| Full restart drill | Monthly | Platform Engineering |
| Evidence pack export + restore | Monthly | Platform Engineering |
| PostgreSQL backup restore (production) | Quarterly | DBA / Cloud Ops |
| Audit log integrity check | Quarterly | Security |
| Full DR simulation (staging) | Bi-annually | Platform Engineering + Security |

---

*This document must be reviewed and updated after any production incident
that results in data loss or service unavailability exceeding the stated RTO.*
