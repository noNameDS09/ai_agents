# ComplianceOS — Operations Runbook

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §4, §7

---

## 1. Local development

### Prerequisites

- Python 3.12+, uv, Node.js 18+
- PostgreSQL 14+ (local or Docker)
- Qdrant (Docker: `docker run -p 6333:6333 qdrant/qdrant`)
- Docker (for Qdrant)

### Setup

```bash
# 1. Copy environment template
cp .env.example .dev.env

# 2. Install dependencies
uv sync

# 3. Provision databases
psql -U postgres -c "CREATE DATABASE agent_dev;"
psql -U postgres -c "CREATE DATABASE agent_test;"

# 4. Start Qdrant
docker run -d -p 6333:6333 --name qdrant qdrant/qdrant

# 5. Run migrations
uv run alembic upgrade head

# 6. Seed reference data (jurisdictions, license types)
uv run python scripts/seed_reference_data.py

# 7. Run tests
uv run pytest

# 8. Start the server
uv run uvicorn src.agent_api.main:app --reload --host 0.0.0.0 --port 8000
```

### Environment variables (compliance-specific)

| Variable | Default | Description |
|----------|---------|-------------|
| `TAVILY_API_KEY` | `""` | Tavily API key for web search tools |
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model name |
| `EMBEDDING_DIM` | `384` | Embedding dimension |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant server URL |
| `EVIDENCE_STORAGE_PATH` | `./data/evidence` | Local evidence file storage |
| `APSCHEDULER_ENABLED` | `true` | Enable scheduled jobs |

## 2. Database operations

### Migrations

```bash
# Create a new migration
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one step
uv run alembic downgrade -1

# Show current revision
uv run alembic current
```

### Audit chain verification

```bash
# Verify audit chain integrity
curl -s -H "X-API-Key: $API_KEY" http://localhost:8000/v1/audit/verify

# Expected response:
# {"status": "ok", "events_checked": 1234, "first_break": null}

# If tampered:
# {"status": "broken", "events_checked": 567, "first_break": {"seq": 568, "occurred_at": "..."}}
```

### Tenant isolation check

```bash
# Run cross-tenant access tests
uv run pytest tests/compliance/test_tenant_isolation.py -v
```

## 3. Job operations

### Scheduled jobs (APScheduler)

| Job | Schedule | Description |
|-----|----------|-------------|
| Regulatory source fetch | Every 6 hours | Fetch updates from configured regulator sources |
| Deadline reminder | Daily 08:00 UTC | Check upcoming license renewals, send reminders |
| Escalation check | Every hour | Escalate overdue remediation tasks |
| Audit chain verification | Daily 00:00 UTC | Verify audit chain integrity |
| Re-index pending versions | Every 15 minutes | Retry `PENDING`/`FAILED` regulation indexing and stale embedding spaces (max 5/run) |

### Manual job triggers

```bash
# Trigger regulatory source fetch
uv run python -m compliance.jobs.tasks fetch_regulations

# Trigger deadline reminder
uv run python -m compliance.jobs.tasks send_reminders

# Trigger escalation check
uv run python -m compliance.jobs.tasks check_escalations
```

### Regulatory ingestion operations (Phase 2)

**Ingest an authoritative document (recommended for statutes/PDF exports):**

```bash
uv run python scripts/ingest_regulation_file.py \
  --file /path/to/ecfr-1022.xml \
  --citation "31 CFR Part 1022" \
  --title "Rules for Money Services Businesses" \
  --jurisdiction US-FEDERAL \
  --publisher "FinCEN (eCFR)" \
  --effective-date 2025-01-01
```

**Check index state:**

```sql
SELECT citation, version_no, index_status, index_collection,
       left(coalesce(index_error, ''), 120) AS error
FROM regulation_versions
ORDER BY ingested_at DESC
LIMIT 20;
```

**Retry a failed version** (also happens automatically every 15 minutes):

```bash
curl -X POST http://localhost:8000/v1/compliance/regulations/versions/<id>/reindex \
  -H "X-API-Key: $API_KEY"
```

**Embedding provider outage**

The free OpenRouter embedding endpoint is intermittently slow (~60–90s) and
returns 504s. Expected behavior:

- Ingest returns `202` with `index_status=PENDING` immediately; indexing happens
  in a background thread so the API stays responsive.
- Transient failures retry with exponential backoff (4 attempts), then mark the
  version `FAILED` with `index_error`. The scheduler retries it.
- Embeddings are cached per process by `(model, sha256(text))`, so re-indexing
  and repeated searches do not repay the latency.
- If the outage is prolonged, switch to `COMPLIANCE_EMBEDDING_PROVIDER=local`
  (requires `uv sync --extra local`) for new ingests; 384-dim vectors live in a
  separate collection and the scheduler re-indexes versions from the other
  embedding space.

**Quality gate: page extraction vs. statute text**

Fetching a regulator *landing page* often returns navigation/boilerplate rather
than legal text, which correctly yields zero obligations (no hallucination).
Before mapping obligations, confirm the stored `raw_text` contains section
numbers and operative language ("shall", "must", dollar thresholds). Prefer
direct document URLs (eCFR API XML, PDFs, statute exports) over index pages.

## 4. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `CREATE EXTENSION vector` fails | pgvector not installed | Use Qdrant instead (recommended) or compile pgvector from source |
| `interrupt()` not resuming | LangGraph checkpoint mismatch | Check thread_id and checkpoint namespace; verify LangGraph version |
| Obligation stuck in `POTENTIALLY_RELEVANT` | No human approval recorded | Review via `/v1/compliance/obligations/review-queue` |
| Audit chain broken | Tampered event or bug | Investigate `first_break` from `/v1/audit/verify`; restore from backup if needed |
| Cross-tenant data leak | Missing `org_id` filter | Audit repository layer; check RLS policies |
| Embedding model OOM | Model too large for available RAM | Use `all-MiniLM-L6-v2` (384-dim, ~80MB) |
| Qdrant connection refused | Qdrant not running | `docker start qdrant` or `docker run -p 6333:6333 qdrant/qdrant` |
| Regulatory fetch fails | Source URL changed or blocked | Check source registry; update URL; verify Tavily MCP access |

## 5. Incident response

### Compliance data breach
1. Revoke all API keys immediately
2. Enable RLS on all tables (if not already)
3. Audit `audit_events` for unauthorized access patterns
4. Notify affected tenants per data breach policy
5. Rotate all secrets

### Audit chain tamper detected
1. Stop all write operations
2. Export audit events to immutable storage (S3 with versioning)
3. Identify the break point from `/v1/audit/verify`
4. Investigate `actor_id` and `occurred_at` of the last valid event
5. Restore from last known-good backup if necessary

### Missed regulatory deadline
1. Identify the obligation and license affected
2. Check if the regulatory source fetch job ran on schedule
3. Verify the rules engine computed the correct deadline
4. Escalate to compliance officer immediately
5. Document in `audit_events` with `event_type = "deadline.missed"`

## 6. Production hardening checklist

- [ ] Install Qdrant (Docker or managed)
- [ ] Configure Alembic migrations (no `init_db()` create-all)
- [ ] Enable Postgres RLS on all tenant-scoped tables
- [ ] Set up RBAC with at least 4 roles (admin, compliance_officer, reviewer, auditor)
- [ ] Enable hash-chained audit events
- [ ] Configure APScheduler for regulatory monitoring
- [ ] Set up evidence storage (S3-compatible)
- [ ] Add structured logging with request IDs and secret redaction
- [ ] Configure TLS at reverse proxy
- [ ] Set up backup and disaster recovery for PostgreSQL and Qdrant
- [ ] Run evaluation harness in CI
- [ ] Set up monitoring (Prometheus/Grafana or equivalent)
- [ ] Configure alerting for missed deadlines and audit chain breaks
- [ ] Document incident response procedures
- [ ] Conduct security review of all service-backed tools (Tavily, file processing)