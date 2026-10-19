# ComplianceOS — AI-Native Financial Compliance Agent System

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](AI-COMPLIANCE.md)
**Base codebase:** `agent-api` (this repository)
**Target stack:** Python 3.12 · FastAPI · LangGraph · PostgreSQL + Qdrant · React/Next.js
**Focus:** Fintech (US), license & deadline management MVP

---

## 1. What we are building

ComplianceOS is an **autonomous compliance operations platform** — not a compliance
chatbot. It continuously answers five operational questions:

1. What regulations apply to this company?
2. What obligations must it satisfy?
3. What has changed since the last review?
4. Where are the compliance gaps and financial risks?
5. What evidence proves that the company is compliant?

The deliverable is a **compliance operation** that runs continuously and produces an
auditable record — not a Q&A interface over documents.

### Non-negotiable engineering principle

> Use an **LLM** for interpreting unstructured regulatory language, extracting
> obligations, matching evidence, and drafting explanations.
> Use **deterministic code** for calculations, permissions, deadline enforcement,
> validation, and workflow transitions.
> Use **RAG** to ground every material conclusion in authoritative source documents
> — and store the precise document version and passages that support it.

Vector similarity alone is never sufficient to determine legal applicability.

---

## 2. Current state audit

### What `agent-api` already provides (reusable foundation)

| Capability | Status | Reuse for ComplianceOS |
|---|---|---|
| FastAPI backend + app factory | Done | Direct — new routers mounted |
| LangGraph agent loop + Postgres checkpointer | Done (0.2.28) | Direct — per-agent graphs |
| PostgreSQL + SQLAlchemy async + asyncpg | Done | Direct — new tables |
| 31 tools (calculator, json, text, encoding, web) | Done | Direct |
| Tavily MCP (web_search, url_extract, web_crawl, web_map, web_research) | Done | Direct — regulatory source retrieval |
| API key auth + rate limiting + CORS + TrustedHost | Done | Needs extension → RBAC |
| Audit events table | Partial | Needs hash-chained immutability |
| React/Vite frontend served same-origin | Done | Reuse shell; new compliance screens |
| Markdown rendering (GFM) | Done | Evidence/audit report rendering |
| 63 passing tests | Done | Baseline |

### Gaps that must be closed

| Gap | Current state | Required for ComplianceOS |
|---|---|---|
| Multi-agent orchestration | Single ReAct loop | Orchestrator routing to 6 specialized agents |
| Human-in-the-loop approval | None | LangGraph `interrupt()` gates for consequential actions |
| Retrieval / RAG | None | Vector store + chunking + citation store |
| Document versioning | None | `RegulationVersion` with immutable snapshots |
| Evidence file storage | None | Object storage + content hashing |
| Tenant isolation | None | Row-level scoping by `org_id`, enforced in queries |
| RBAC | Single shared API key | Roles: compliance_officer, reviewer, auditor, admin |
| Tamper-evident audit | Append-only rows | Hash-chained events (prev_hash → event_hash) |
| Background jobs | None | Celery (or APScheduler for MVP) for scheduled monitoring |
| Deadline computation | None | Deterministic rules engine w/ jurisdiction rules |
| Prompt-injection defense | Not addressed | Untrusted-document isolation, instruction/data separation |
| Evaluations | None | Extraction accuracy, missed obligations, citation correctness |

### Technical constraints discovered

- **PostgreSQL 18.6**, only `plpgsql` installed. `pgvector` is NOT available as an
  extension. `pg_trgm` IS available. → See §3 for vector store decision.
- **LangGraph 0.2.28** installed. `interrupt()` exists but is fragile. Upgrade
  path must be validated before approval workflow.
- **Docker** is available — can run Qdrant locally.
- Tavily MCP is already integrated and verified working against the live server.

---

## 3. Embedding & vector store decision

### 3.1 Embedding provider comparison

Verified against OpenRouter's live API (`/api/v1/embeddings/models`) — OpenRouter
exposes 33 embedding models, 3 of which are free:

| Option | Dim | Cost | Health | Verdict |
|---|---|---|---|---|
| **OpenRouter `nvidia/llama-nemotron-embed-vl-1b-v2:free`** | 2048 | $0 | 99.97% (3-day) | ✅ **Recommended** |
| OpenRouter `nvidia/nemotron-3-embed-1b:free` | 2048 | $0 | 69.17% (3-day, intermittent) | ⚠️ Unstable |
| OpenRouter `liquid/lfm-2.5-embedding-350m:free` | 1024 | $0 | Unconfirmed | ⚠️ Lower dim |
| Local sentence-transformers (`all-MiniLM-L6-v2`) | 384 | $0 | N/A (local) | ⚠️ Fallback for sensitive data |
| Paid embedding API (OpenAI, Cohere, Voyage) | varies | $/token | N/A | ❌ Violates "free inference only" |
| EmbeddingGemma 2 (Google, 740M params) | 768 | $0 (local) | N/A | ⚠️ Upgrade path if quality needed |

**Decision: OpenRouter `nvidia/llama-nemotron-embed-vl-1b-v2:free` (primary)**

Rationale:
1. **Free**: $0 cost, aligns with "free inference only" constraint.
2. **High quality**: 2048-dim dedicated embedding model (vs 384-dim general-purpose).
3. **No heavy dependencies**: No PyTorch/transformers needed — just an HTTP call.
   Removes ~2GB of dependencies from the base stack.
4. **High availability**: 99.97% reported uptime over 3 days.
5. **OpenAI-compatible**: Uses the same `/api/v1/embeddings` endpoint pattern as
   chat completions — trivial integration with existing OpenRouter client.

**Hybrid privacy policy:**
- **Public regulatory text** (statutes, rules, filings — all public information)
  → OpenRouter embeddings. No sensitive data leaves the server.
- **Sensitive evidence** (client financial data, internal documents)
  → Local `sentence-transformers/all-MiniLM-L6-v2` (optional, only if needed).
  Configured via `EMBEDDING_PROVIDER` setting: `openrouter` (default) or `local`.

This is a change from the earlier "local only" recommendation. The discovery that
OpenRouter serves free, high-quality embedding models with 99.97% uptime makes
the all-OpenRouter approach the clear winner for MVP. Local fallback remains
available for privacy-sensitive use cases.

### 3.2 Vector store comparison

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Qdrant (self-hosted via Docker)** | Purpose-built vector DB; free; fast (Rust); filtering on payload; runs locally; no data leaves server | Adds a service (Docker container); another thing to operate | ✅ **Recommended for MVP** |
| **pgvector** | Co-located with Postgres; single DB to manage; SQL joins with vectors | **Not installed on this Postgres instance**; requires compilation from source; heavier queries | ❌ Not available on this system |
| **Qdrant Cloud (free tier)** | Managed, no ops; 1GB RAM / 4GB disk; ~1M 768-dim vectors | Data leaves server; free tier limits; network dependency | ⚠️ Dev only |
| **ChromaDB** | Simple, Python-native, embedded | Less production-ready; weaker filtering; single-node only | ⚠️ Dev/prototype only |
| **PostgreSQL full-text search + pg_trgm** | Already installed; no new service | Keyword-only, no semantic search; poor recall for paraphrased queries | ⚠️ Fallback if Qdrant unavailable |

**Decision: Self-hosted Qdrant via Docker**

Rationale:
1. **pgvector is not available** on this PostgreSQL instance — it would require
   compiling from source, which is fragile and hard to reproduce.
2. **Privacy**: Self-hosted Qdrant keeps all embeddings and regulatory documents
   on the same machine. No data leaves the server.
3. **Purpose-built**: Qdrant is designed for vector search with payload filtering —
   critical for compliance (filter by jurisdiction, obligation type, date range).
4. **Free and simple**: `docker run -p 6333:6333 qdrant/qdrant` — no credit card,
   no signup, no configuration.
5. **Upgrade path**: Migrate to Qdrant Cloud (free tier → standard) when scaling
   beyond single-node, or install pgvector if the team prefers a single database.

### 3.3 Embedding + vector store summary

```
Regulatory documents → deterministic chunker → sentence-transformers (local, CPU)
                                                    ↓
                                          all-MiniLM-L6-v2 (384-dim)
                                                    ↓
                                          Qdrant (self-hosted via Docker)
                                                    ↓
                                          RAG retrieval with citation
```

Everything runs locally. No external API calls for embeddings. No data leaves the server.

---

## 4. Target architecture

### 4.1 Agent topology

```
                     ┌──────────────────────────┐
                     │   Compliance Control     │
                     │   Center (Next.js)       │
                     │  obligations · risk ·    │
                     │  deadlines · approvals   │
                     └────────────┬─────────────┘
                                  │
                     ┌────────────▼─────────────┐
                     │  Compliance Orchestrator │
                     │  (LangGraph supervisor)  │
                     │  plans · routes · retries│
                     │  state · permissions     │
                     └──┬──┬──┬──┬──┬──┬────────┘
                        │  │  │  │  │  │
        ┌───────────────┘  │  │  │  │  └──────────────┐
        ▼                  ▼  ▼  ▼  ▼                 ▼
 ┌────────────┐  ┌────────────┐ ┌────────┐ ┌────────────┐ ┌────────────┐
 │ Regulatory │  │ Obligation │ │ Risk & │ │ License &  │ │ Evidence & │
 │ Intelligence│ │  Mapping   │ │ Anomaly│ │  Deadline  │ │   Audit    │
 └──────┬─────┘  └─────┬──────┘ │ Detect │ └─────┬──────┘ └─────┬──────┘
        │              │        └───┬────┘       │              │
        │              │            │            │              │
        │              │      ┌─────▼─────┐      │              │
        │              │      │ Reporting │      │              │
        │              │      │   Agent   │      │              │
        │              │      └───────────┘      │              │
        └──────────────┴────────────┴────────────┴──────────────┘
                                  │
        ┌─────────────────────────▼──────────────────────────┐
        │        Shared Compliance Intelligence Layer        │
        │  Regulatory KB · Policy Graph · Evidence Store ·  │
        │  Rules Engine · Immutable Audit Chain · Approvals  │
        └────────────────────────────────────────────────────┘
```

### 4.2 Agent contracts

| Agent | Reads | Writes | May call tools | Requires approval |
|---|---|---|---|---|
| Regulatory Intelligence | regulator sources | `RegulationVersion` | web_search, url_extract, web_crawl, web_map | No (ingest only) |
| Obligation Mapping | `RegulationVersion` + org profile | `Obligation` (proposed) | RAG retrieve | **Yes** — before obligation becomes active |
| Risk & Anomaly | transactions, controls | `ComplianceFinding` | RAG retrieve, rules | **Yes** — before severity ≥ high published |
| License & Deadline | licenses, rules | `RemediationTask` | date_diff, cron_describe | **Yes** — before status change to filed/closed |
| Evidence & Audit | obligations, evidence store | `Evidence`, audit packages | csv_parse, json_get, text_transform | **Yes** — before package marked final |
| Reporting | findings, tasks, approvals | reports | text_transform | No (draft only) |

### 4.3 Orchestrator design

A single LangGraph supervisor state machine:

```
START → LOAD_CONTEXT → CLASSIFY_INTENT → PLAN → DISPATCH ──┬─→ [agent] ─→ COLLECT ─→ EVALUATE_RETRY? ─┐
                                                          │                                    ↑              │
                                                          └────────────────────────────────────┴──────────────┘
  → REQUEST_APPROVAL (interrupt() — park until human decision)
  → PERSIST (write results + audit chain entries)
END
```

Rules:
- **No agent may skip another agent's gate.** Obligation Mapping cannot persist
  without Regulatory Intelligence having produced a `RegulationVersion`.
- **Retry policy**: bounded retries per agent (default 2); failures escalate to
  human task, never silently dropped.
- **Permission enforcement**: every state transition validated against RBAC role.
- **Idempotency**: each run keyed by `(thread_id, plan_hash)`.

---

## 5. Data model

Twelve core entities. Relationships matter more than agent count.

### 5.1 Tables

```
organizations (id PK, legal_name, industry, created_at, updated_at)
  └── legal_entities (id PK, org_id FK, name, registration_no, country, state, status)
        └── licenses (id PK, entity_id FK, license_type, authority, jurisdiction_id FK,
                      issued_on, expires_on, status, renewal_window_days, document_id FK)
              └── evidence (id PK, org_id FK, kind, filename, storage_uri,
                            content_sha256, mime_type, size_bytes, uploaded_by,
                            collected_at)

jurisdictions (id PK, code, name, country, regime, regulator_url, active)

regulation_versions (id PK, jurisdiction_id FK, citation, title, source_url,
                     publisher, publication_date, effective_date, version_no,
                     supersedes_id FK, raw_text, content_sha256, ingested_at,
                     ingested_by, UNIQUE (citation, version_no))
  └── regulation_chunks (id PK, regulation_version_id FK, chunk_index, text,
                         token_count, embedding vector(384), page_ref, char_start)
  └── obligations (id PK, org_id FK, regulation_version_id FK, citation,
                   normalized_text, applicability (POTENTIALLY_RELEVANT|CONFIRMED|NOT_APPLICABLE),
                   status (DRAFT|ACTIVE|SUPERSEDED|RETRACTED),
                   responsible_entity_id FK, citation_chunk_ids UUID[],
                   created_by, created_at, approved_by, approved_at)
        └── controls (id PK, org_id FK, name, description, control_type,
                      frequency, owner_entity_id FK, status, created_at)
              └── control_obligations (control_id FK, obligation_id FK,
                                       coverage (FULL|PARTIAL|NONE), assessed_by,
                                       assessed_at, evidence_ids UUID[])
        └── compliance_findings (id PK, org_id FK, obligation_id FK, control_id FK,
                                 finding_type (GAP|ANOMALY|CONTROL_FAILURE|EXPIRY),
                                 severity (LOW|MEDIUM|HIGH|CRITICAL),
                                 description, status (OPEN|ACKNOWLEDGED|REMEDIATED|ACCEPTED),
                                 evidence_ids UUID[], detected_at, resolved_at)
              └── remediation_tasks (id PK, org_id FK, finding_id FK, obligation_id FK,
                                     title, description, owner_user_id FK,
                                     due_date, escalation_level, status
                                     (PENDING|IN_PROGRESS|BLOCKED|DONE|CANCELLED),
                                     completed_at, resolution_note)
        └── approvals (id PK, org_id FK, subject_type, subject_id,
                       decision (APPROVED|REJECTED|CHANGES_REQUESTED|REVIEW_REQUIRED),
                       reviewer_user_id FK, rationale, decided_at,
                       previous_approval_hash, approval_hash)
        └── audit_events (id PK, org_id FK, actor_type (AGENT|USER|SYSTEM),
                          actor_id, event_type, subject_type, subject_id,
                          payload JSONB, prev_event_hash, event_sha256,
                          occurred_at, seq BIGSERIAL)
```

### 5.2 Invariants (enforced in code + DB constraints)

1. `audit_events` is **append-only** — revoke UPDATE/DELETE from the application
   role; hash chain `event_sha256 = H(prev_event_hash || payload)`.
2. `regulation_versions` is **immutable** once ingested. A change creates a new
   `version_no` with `supersedes_id` pointing at the prior version.
3. An `obligation` with `applicability = CONFIRMED` **must** have ≥1 citation chunk
   and `approved_by IS NOT NULL`.
4. A `compliance_finding` with `severity IN (HIGH, CRITICAL)` **must** reference at
   least one `evidence` row.
5. Every `remediation_task.due_date` is computed by the rules engine, never by an LLM.

---

## 6. Trust & safety model

| Requirement | Implementation |
|---|---|
| **Source provenance** | Every finding/obligation stores `regulation_version_id` + `citation_chunk_ids`. Citation renders to exact quoted text. |
| **No unsupported conclusions** | Applicability defaults to `POTENTIALLY_RELEVANT`. Only human approval promotes to `CONFIRMED`. Uncertain → `REVIEW_REQUIRED`, never silently settled. |
| **Human approval** | LangGraph `interrupt()` before: obligation activation, high/critical finding publication, license status change, audit package finalization. |
| **Tenant isolation** | Every table carries `org_id`. Repository layer requires `org_id` in every query (no implicit "current org"). Postgres RLS as defense-in-depth. |
| **Tamper-evident audit** | Hash-chained append-only `audit_events`. Verification endpoint re-walks the chain and reports the first break. |
| **Prompt-injection defense** | Retrieved regulatory text and uploaded evidence are wrapped as **data**, never instructions. Tool outputs from `url_extract`/`web_search` are fenced and stripped of instruction-like content before reaching the LLM. Raw HTML never reaches the LLM. |
| **Deterministic escape hatch** | Calculations, deadlines, permission checks, state transitions run in Python — never `eval`, never LLM-parsed. |
| **Evaluation** | Golden dataset of regulations → expected obligations. Metrics: extraction precision/recall, missed-obligation rate, citation correctness, false-positive rate, time-to-detect. |

---

## 7. Phased roadmap

### Phase 0 — Foundations (blocking)

Nothing else starts until this lands.

| # | Deliverable | Exit criteria |
|---|---|---|
| 0.1 | Install Qdrant (Docker) + sentence-transformers; embedding config | `docker run qdrant/qdrant` works; embedding round-trip test passes; `all-MiniLM-L6-v2` (384-dim) |
| 0.2 | Alembic migrations replace `init_db()` create-all | `alembic upgrade head` from empty DB; downgrade tested |
| 0.3 | Org scoping: add `org_id` to all tables + repository layer | No query can read cross-tenant; RLS policies created |
| 0.4 | RBAC: `users`, `roles`, dependency `require_role(...)` | Unauthenticated → 401; wrong role → 403; role matrix tested |
| 0.5 | Hash-chained `audit_events` + `GET /v1/audit/verify` | Tamper with one row → verifier reports break at correct offset |
| 0.6 | LangGraph upgrade decision (0.2.28 → 0.3+/1.x) | `interrupt()`/checkpoint APIs verified; all 63 existing tests pass |
| 0.7 | Evidence storage adapter (local FS → S3-compatible) | Store/retrieve/hash round-trip; large-file streaming |

### Phase 1 — MVP: License & deadline management

**Scope:** one customer segment, one narrow workflow — track business licenses,
renewal dates, jurisdiction-specific obligations, supporting documents, escalation.

**Fintech focus (US):** Money Transmitter Licenses (MTL), state-by-state,
plus FinCEN registration, state lending licenses, and broker-dealer registrations.

| # | Deliverable | Exit criteria |
|---|---|---|
| 1.1 | Core tables: organizations, legal_entities, jurisdictions, licenses, evidence | Migration + model tests; FK constraints validated |
| 1.2 | Deterministic rules engine (jurisdiction → renewal window, grace period, escalation ladder) | 100% pure-function unit tests; no LLM in path; golden test per jurisdiction |
| 1.3 | LangGraph License & Deadline agent sub-graph | Computes upcoming renewals, creates `RemediationTask`; checkpointed |
| 1.4 | REST API: CRUD licenses, list deadlines, acknowledge/resolve tasks | OpenAPI schema; contract tests |
| 1.5 | Approval gate via `interrupt()` for status transitions | Approval parks graph; resumes on decision; audit-chained |
| 1.6 | Frontend: License dashboard, deadline timeline, task board | Reuses existing shell; accessible; responsive |
| 1.7 | Reminder job (APScheduler for MVP) | Idempotent; emits notifications; respects escalation ladder |

**Phase 1 exit metric:** missed renewal rate = 0 in a 90-day simulated run.

### Phase 2 — Regulatory change monitoring

**Scope:** detect updates, compare versions, surface potentially affected obligations.

| # | Deliverable | Exit criteria |
|---|---|---|
| 2.1 | Regulatory source registry + fetch job (Tavily MCP + direct regulator URLs) | Source list configurable; fetch idempotent by `content_sha256` |
| 2.2 | `RegulationVersion` + change detection (diff vs `supersedes_id`) | Same content → no new version; changed content → new version |
| 2.3 | Chunking + embedding pipeline | Deterministic chunk boundaries; citation resolves to exact text |
| 2.4 | Regulatory Intelligence agent | Ingests, stores version, reports change summary with citations |
| 2.5 | Obligation Mapping agent (always `POTENTIALLY_RELEVANT` initially) | Precision ≥ 0.9 on golden dataset; zero unapproved `CONFIRMED` |
| 2.6 | Review queue UI (approve/reject with rationale) | Approval writes to chain; rejection removes obligation |

**Phase 2 exit metric:** recall ≥ 0.85; every proposed obligation carries ≥1
resolvable citation; citation correctness 100%.

### Phase 3 — Evidence, controls, audit packages

| # | Deliverable | Exit criteria |
|---|---|---|
| 3.1 | `controls` + `control_obligations` coverage assessment | Coverage enum; assessment audit-chained |
| 3.2 | Evidence Agent (request → completeness check → gap detection) | Missing-evidence detection on seeded fixtures |
| 3.3 | Compliance findings (gap/anomaly/expiry) with severity rules | Severity computed by deterministic rules, not LLM |
| 3.4 | Reporting Agent → deterministic audit package | Reproducible from stored data; includes requirement, source version, applicability, evidence, remediation history, approvals |
| 3.5 | Risk dashboard | Findings by severity, trend, drill-down to citation + evidence |
| 3.6 | Evaluation harness | Runs golden dataset in CI; regression gate on precision/recall/citations |

**Phase 3 exit metric:** time-to-prepare-audit-package < 2 hours (from days).

### Phase 4+ — Deferred (post-MVP)

Risk & Anomaly Detection (transaction surveillance), background job infrastructure
at scale (Celery/Temporal), multi-jurisdiction expansion, integrations (accounting
platforms, document repositories), continuous control monitoring.

---

## 7. Repository changes

```
ai_agents/                        # this repo — becomes the ComplianceOS backend
├── src/agent_api/                # existing generic agent (retained, unchanged)
│   └── ...
├── src/compliance/               # NEW — compliance domain
│   ├── __init__.py
│   ├── config.py                 # compliance-specific settings
│   ├── models/                   # SQLAlchemy models per entity group
│   │   ├── organization.py       # orgs, legal entities, jurisdictions
│   │   ├── licensing.py          # licenses, evidence
│   │   ├── regulatory.py         # regulation versions, chunks, obligations
│   │   ├── controls.py           # controls, coverage, findings
│   │   ├── tasks.py              # remediation tasks, approvals
│   │   └── audit.py              # hash-chained audit events
│   ├── schemas/                  # Pydantic API + agent I/O schemas
│   ├── agents/                   # 6 agent sub-graphs
│   │   ├── base.py               # AgentContract, common sub-graph factory
│   │   ├── regulatory_intelligence.py
│   │   ├── obligation_mapping.py
│   │   ├── risk_detection.py
│   │   ├── license_deadline.py
│   │   ├── evidence_audit.py
│   │   └── reporting.py
│   ├── orchestrator/
│   │   ├── graph.py              # supervisor state machine
│   │   ├── planner.py            # intent classification + task DAG
│   │   └── approvals.py          # interrupt()/resume, approval gates
│   ├── services/                 # deterministic code — no LLM
│   │   ├── rules_engine.py       # jurisdiction rules, deadline math
│   │   ├── permissions.py        # RBAC evaluation
│   │   ├── audit_chain.py        # hash chaining + verification
│   │   ├── evidence_store.py     # object storage adapter
│   │   ├── retrieval.py          # RAG retrieve + citation resolution
│   │   └── diffing.py            # regulation version diffing
│   ├── rag/
│   │   ├── chunking.py           # deterministic chunker
│   │   ├── embeddings.py         # sentence-transformers (local, CPU)
│   │   └── prompts/              # versioned prompt templates
│   ├── api/
│   │   └── v1/                   # compliance routers
│   └── jobs/                     # scheduled/background
│       ├── scheduler.py          # APScheduler (MVP)
│       └── tasks.py              # fetch, digest, reminder jobs
├── alembic/                      # NEW — migrations
├── frontend/                     # existing shell; new compliance screens
├── docker-compose.yml            # NEW — Postgres + Qdrant
└── docs/                         # this plan + new architecture docs
```

### New dependencies (proposed)

| Package | Purpose | Phase |
|---|---|---|
| `alembic` | Migrations | 0.2 |
| `sentence-transformers` | Local embeddings (all-MiniLM-L6-v2, 384-dim) | 0.1 |
| `qdrant-client` | Qdrant vector store client | 0.1 |
| `apscheduler` | Scheduled jobs (MVP) | 1.7 |
| `celery` + `redis` | Background jobs at scale | 4+ |
| `pypdf` | PDF text extraction for evidence | 3 |
| `pytest-postgresql` | Isolated test DBs per run | 0.2 |

### Frontend

Keep the existing React/Vite setup for the backend-served shell. ComplianceOS
(control center) is dashboard-heavy and likely warrants **Next.js** as a separate
app talking to the compliance API — decision deferred to Phase 1.6.

---

## 8. Documentation to create

| Doc | Contents |
|---|---|
| `docs/ai-compliance/COMPLIANCE-ARCHITECTURE.md` | System architecture: agents, orchestrator, shared intelligence layer, data flow |
| `docs/ai-compliance/COMPLIANCE-DATA-MODEL.md` | Entity definitions, ER diagram, invariants, migrations policy |
| `docs/ai-compliance/COMPLIANCE-TRUST-MODEL.md` | Provenance, approvals, tamper-evidence, prompt-injection defense, tenant isolation |
| `docs/ai-compliance/COMPLIANCE-AGENTS.md` | Per-agent contract: I/O schemas, tool allowlists, approval requirements, retry policy |
| `docs/ai-compliance/COMPLIANCE-API.md` | REST API reference for compliance endpoints |
| `docs/ai-compliance/COMPLIANCE-RULES-ENGINE.md` | Jurisdiction rule specification, deadline math, escalation ladders |
| `docs/ai-compliance/COMPLIANCE-EVALUATION.md` | Golden dataset, metrics definitions, regression gates |
| `docs/ai-compliance/COMPLIANCE-RUNBOOK.md` | Ops: migrations, job failures, audit verification, incident response |

Existing `docs/` files (`ARCHITECTURE.md`, `API.md`, `SECURITY.md`, …) remain scoped
to the generic `agent_api` and are cross-referenced, not merged.

---

## 9. Success metrics

Track these from Phase 1 onward — they are the definition of done, not vanity metrics.

| Metric | Target | Measured by |
|---|---|---|
| Missed renewal rate | 0% | Simulated 90-day run |
| Time to identify a regulatory change | < 24h | `regulation_versions.ingested_at − publication_date` |
| Time to prepare an audit package | < 2h | Package generation timestamp delta |
| Obligation extraction precision | ≥ 0.90 | Golden dataset |
| Obligation extraction recall | ≥ 0.85 | Golden dataset |
| Citation correctness | 100% | Every citation resolves to exact source text |
| False-positive rate | < 10% | Reviewed obligations vs confirmed |
| Manual hours eliminated | Baseline-relative | Time-tracking study |

---

## 10. Open questions

1. **Embedding provider** — ✅ **RESOLVED**: OpenRouter free embedding models exist
   (3 available: `nvidia/llama-nemotron-embed-vl-1b-v2:free` (2048-dim, 99.97%),
   `nvidia/nemotron-3-embed-1b:free` (2048-dim, 69.17%), `liquid/lfm-2.5-embedding-350m:free`
   (1024-dim)). Selected: `nvidia/llama-nemotron-embed-vl-1b-v2:free`. Verified via live
   API call — returns 2048-dim embeddings at $0 cost. Hybrid fallback to local
   sentence-transformers for sensitive evidence (optional).
2. **Vector store** — ✅ **RESOLVED**: pgvector not available on this Postgres 18.6.
   Qdrant (self-hosted via Docker) selected. Verified: `docker run -p 6333:6333 qdrant/qdrant`.
3. **Jurisdiction scope for MVP** — which US state(s) and license types? Determines
   the rules-engine surface in Phase 1.2. (Fintech focus confirmed: MTL, state lending,
   broker-dealer, FinCEN registration.)
2. **LangGraph upgrade** — 0.2.28's `interrupt()` is the weakest link for approval
   workflows. Upgrade path must be validated in Phase 0.6.
3. **Frontend split** — extend the existing Vite SPA, or a separate Next.js control
   center? Decide in Phase 1.6.
4. **Evidence file types** — PDF only for MVP, or DOCX/XLSX too? Affects Phase 3.1.
5. **Multi-tenancy model** — separate database per org vs shared schema + RLS.
   Recommendation: shared schema + RLS for operational simplicity.

---

## 11. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hallucinated legal conclusions presented as settled law | High | Applicability defaults to `POTENTIALLY_RELEVANT`; only human approval yields `CONFIRMED`; citations mandatory |
| Prompt injection via a regulator PDF | Medium | Treat all retrieved/uploaded text as data; strip instruction-like patterns; never pass raw HTML to the LLM |
| Silent obligation misses (recall failure) | High | Golden dataset regression gate; `REVIEW_REQUIRED` queue for low-confidence cases |
| Audit chain tamper | Low | Hash chaining + append-only role permissions + verifier endpoint |
| Cross-tenant data leak | Medium | Mandatory `org_id` scoping + Postgres RLS + integration tests attempting cross-tenant reads |
| Rule engine drift when jurisdictions change | Medium | Rules are data (versioned tables), not code; rules changes are themselves audited |
| Free-tier model quality insufficient for legal extraction | Medium | Phase 0 evaluation of free models; if inadequate, require a paid model for compliance reasoning and document the cost tradeoff |
| Qdrant service unavailable | Low | Self-hosted via Docker; health check + graceful degradation to keyword search |

---

## 12. Immediate next steps

1. Decide open questions 1, 3, 5 (jurisdiction, LangGraph upgrade, frontend split).
2. Execute **Phase 0** (extensions, migrations, tenancy, RBAC, audit chain, LangGraph upgrade).
3. Create the Phase 0 architecture docs listed in section 8.
4. Begin **Phase 1.1–1.3** (core tables, rules engine, License & Deadline agent).

---

## Appendix — Relationship to `agent-api`

`agent-api` is **not** being replaced. It remains the generic, reusable agent
runtime: FastAPI app factory, LangGraph loop, Postgres checkpointer, tool framework,
auth middleware, and the React shell. ComplianceOS is a **domain application built
on top of it**, importing `agent_api`'s infrastructure (config, database, security
primitives, tool registry pattern) while adding its own domain models, agents,
orchestrator, and trust model.

---

## Appendix — Embedding & vector store decision summary

### Embedding provider: Local sentence-transformers (all-MiniLM-L6-v2, 384-dim)

- **Why not OpenRouter?** No embedding models exist on OpenRouter (verified — 0
  results for "embed" across 471 models).
- **Why not a paid API?** Violates "free inference only" constraint; data leaves server.
- **Why not EmbeddingGemma?** 740M params is too heavy for CPU-only MVP. Upgrade
  path for Phase 2 if quality is insufficient.
- **all-MiniLM-L6-v2**: 384-dim, ~50ms/embedding on CPU, strong MTEB scores,
  Apache 2.0 license, ~80MB model size.

### Vector store: Qdrant (self-hosted via Docker)

- **Why not pgvector?** Not installed on this Postgres 18.6 instance. Compiling
  from source is fragile and hard to reproduce.
- **Why not Qdrant Cloud?** Data leaves server (privacy concern for compliance).
  Free tier has 1GB RAM / 4GB disk limit.
- **Why not ChromaDB?** Less production-ready; weaker filtering; single-node only.
- **Qdrant via Docker**: `docker run -p 6333:6333 qdrant/qdrant` — free, no
  credit card, no signup, no configuration. Purpose-built for vector search with
  payload filtering. Keeps all data on-server. Upgrade to Qdrant Cloud when scaling.

### Stack summary

```
Regulatory documents → deterministic chunker → sentence-transformers (local, CPU)
                                                    ↓
                                          all-MiniLM-L6-v2 (384-dim)
                                                    ↓
                                          Qdrant (self-hosted via Docker)
                                                    ↓
                                          RAG retrieval with citation
```

Everything runs locally. No external API calls for embeddings. No data leaves the server.