# ComplianceOS — System Architecture

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §4
**Plan:** [COMPLIANCE-PLAN.md](COMPLIANCE-PLAN.md)

---

## 1. Overview

ComplianceOS is a domain application built on top of the generic `agent-api` runtime.
It adds a compliance domain layer (`src/compliance/`) with 6 specialized agents, a
supervisor orchestrator, a shared compliance intelligence layer, and a Next.js
control center frontend.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Compliance Control Center                         │
│                    (Next.js · React · TypeScript)                       │
│         obligations · risk scores · deadlines · approvals · audit       │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS (same-origin or CORS)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Compliance API                            │
│   /v1/compliance/*  (org-scoped, RBAC, audit-chained)                   │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                     Compliance Orchestrator (LangGraph)                 │
│  LOAD_CONTEXT → CLASSIFY_INTENT → PLAN → DISPATCH → COLLECT → APPROVE  │
│  → PERSIST (audit chain)                                               │
└──┬──┬──┬──┬──┬──┬──────────────────────────────────────────────────────┘
   │  │  │  │  │  │
   ▼  ▼  ▼  ▼  ▼  ▼
┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐┌──────┐
│Reg   ││Oblig ││Risk  ││Lic   ││Evid  ││Report│
│Intel ││Map   ││&Anom ││&Dead ││&Audit││ing   │
└──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘└──┬───┘
   │       │       │       │       │       │
   └───────┴───────┴───────┴───────┴───────┘
                    │
┌───────────────────▼─────────────────────────────────────────────────────┐
│                   Shared Compliance Intelligence Layer                    │
│  Regulatory KB · Policy Graph · Evidence Store · Rules Engine ·          │
│  Immutable Audit Chain · Human Approvals · Qdrant (RAG)                  │
└─────────────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐
│  PostgreSQL  │  │   Qdrant     │  │  Object Storage      │
│  (12 tables) │  │  (vectors)   │  │  (evidence files)    │
│  + RLS       │  │  (Docker)    │  │  (local/S3)          │
└──────────────┘  └──────────────┘  └──────────────────────┘
```

## 1. Layers

| Layer | Responsibility | Key files |
|-------|----------------|-----------|
| **API** | HTTP request/response, auth (RBAC), rate limiting, validation | `src/compliance/api/v1/` |
| **Orchestrator** | Supervisor state machine, planning, routing, retries, approval gates | `src/compliance/orchestrator/` |
| **Agents** | 6 specialized LangGraph sub-graphs with typed I/O | `src/compliance/agents/` |
| **Services** | Deterministic code — rules, permissions, audit chain, retrieval, diffing | `src/compliance/services/` |
| **RAG** | Chunking, embeddings (sentence-transformers), Qdrant retrieval | `src/compliance/rag/` |
| **Data** | SQLAlchemy models, Alembic migrations, evidence storage adapter | `src/compliance/models/` |
| **Jobs** | Scheduled monitoring, reminders, escalation | `src/compliance/jobs/` |
| **Config** | Compliance-specific settings (jurisdictions, rules, thresholds) | `src/compliance/config.py` |

## 2. Data flow for one regulatory change

```
1. INGEST      Regulatory Intelligence retrieves update from official regulator.
               Stores: source_url, publisher, publication_date, effective_date,
               raw_text, content_hash, version_number.

2. MAP         Obligation Mapping checks which LegalEntity / License / activity
               is affected. Distinguishes POTENTIALLY_RELEVANT from CONFIRMED.
               Output carries citation: (regulation_version_id, chunk_ids).

3. GAPS        System compares new requirement against existing Control, License,
               and Evidence. Produces ComplianceFinding with severity + citations.

4. REMEDIATE   Rules engine creates RemediationTask, assigns owner, computes
               deadline from jurisdiction rules, starts escalation schedule.

5. EVIDENCE    Evidence Agent requests documents, checks completeness, identifies
               gaps, links each finding to supporting evidence (content-hashed).

6. AUDIT PKG   Reporting Agent assembles: requirement text → source version →
               applicability decision → control evidence → remediation history →
               reviewer approvals. Output is a deterministic PDF/JSON artifact.
```

## 3. Agent topology

### 3.1 Agent contracts

Every agent:

1. Has a **typed input schema** and **typed output schema** (Pydantic v2).
2. Declares which **tools** it may call (its own allowlist, not the global one).
3. Runs inside a **LangGraph sub-graph** with its own checkpoint namespace.
4. Writes every material conclusion to the **audit chain**.
5. Never transitions workflow state directly — it requests a transition, and the
   rules engine validates it.

| Agent | Reads | Writes | May call tools | Requires approval |
|---|---|---|---|---|
| Regulatory Intelligence | regulator sources | `RegulationVersion` | web_search, url_extract, web_crawl, web_map | No (ingest only) |
| Obligation Mapping | `RegulationVersion` + org profile | `Obligation` (proposed) | RAG retrieve | **Yes** — before obligation becomes active |
| Risk & Anomaly | transactions, controls | `ComplianceFinding` | RAG retrieve, rules | **Yes** — before severity ≥ high published |
| License & Deadline | licenses, rules | `RemediationTask` | date_diff, cron_describe | **Yes** — before status change to filed/closed |
| Evidence & Audit | obligations, evidence store | `Evidence`, audit packages | csv_parse, json_get, text_transform | **Yes** — before package marked final |
| Reporting | findings, tasks, approvals | reports | text_transform | No (draft only) |

### 3.2 Orchestrator design

A single LangGraph supervisor state machine:

```
START
  → LOAD_CONTEXT      (org, entities, jurisdictions, active obligations)
  → CLASSIFY_INTENT   (LLM: which agents does this task need?)
  → PLAN              (deterministic: ordered DAG of agent invocations)
  → DISPATCH ──┬─→ [agent sub-graph] ─→ COLLECT ─→ EVALUATE_RETRY? ─┐
               │                                    ↑              │
               └────────────────────────────────────┴──────────────┘
  → REQUEST_APPROVAL  (interrupt() — park until human decision)
  → PERSIST           (write results + audit chain entries)
END
```

Rules the orchestrator must enforce:

- **No agent may skip another agent's gate.** Obligation Mapping output cannot be
  persisted without Regulatory Intelligence having produced a `RegulationVersion`.
- **Retry policy**: bounded retries per agent (default 2); failures escalate to a
  human task, never silently dropped.
- **Permission enforcement**: every state transition validated against the actor's
  RBAC role before execution.
- **Idempotency**: each run keyed by `(thread_id, plan_hash)` so re-running a failed
  workflow does not duplicate obligations.

## 4. Shared compliance intelligence layer

| Component | Purpose | Implementation |
|---|---|---|
| Regulatory KB | Versioned regulatory documents + chunks + embeddings | PostgreSQL + Qdrant |
| Policy graph | Company policies, controls, their relationships | PostgreSQL (relational) |
| Evidence store | Documents, transactions, attestations, source references | Object storage + content hashing |
| Rules engine | Jurisdiction-specific rules, deadline math, escalation ladders | Deterministic Python, versioned data tables |
| Immutable audit chain | Append-only hash-chained event log | PostgreSQL, revoking UPDATE/DELETE from app role |
| Human approvals | Reviewer decisions with rationale and timestamp | PostgreSQL + LangGraph `interrupt()` |

## 5. Technology stack

| Layer | Technology | Notes |
|---|---|---|
| Frontend | Next.js (recommended) or existing React/Vite | Decision deferred to Phase 1.6 |
| Backend API | FastAPI (existing) | New compliance routers mounted |
| Agent orchestration | LangGraph (upgrade from 0.2.28 to 0.3+/1.x) | `interrupt()` for approvals |
| Database | PostgreSQL 18.6 | 12 compliance tables + RLS |
| Vector store | Qdrant (self-hosted via Docker) | pgvector not available on this instance |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2, 384-dim) | Local, CPU, free, private |
| Object storage | Local FS → S3-compatible | Evidence files, content-hashed |
| Background jobs | APScheduler (MVP) → Celery + Redis (scale) | Scheduled monitoring, reminders |
| Migrations | Alembic | Replace `init_db()` create-all |
| Testing | pytest + pytest-postgresql | Isolated test DBs |

## 6. Relationship to `agent-api`

`agent-api` is **not** being replaced. It remains the generic, reusable agent
runtime: FastAPI app factory, LangGraph loop, Postgres checkpointer, tool framework,
auth middleware, and the React shell. ComplianceOS is a **domain application built
on top of it**, importing `agent_api`'s infrastructure (config, database, security
primitives, tool registry pattern) while adding its own domain models, agents,
orchestrator, and trust model.

```
src/
├── agent_api/          # generic runtime (unchanged)
└── compliance/         # NEW — compliance domain
    ├── models/         # 12 entity groups
    ├── schemas/        # Pydantic API + agent I/O
    ├── agents/         # 6 agent sub-graphs
    ├── orchestrator/   # supervisor state machine
    ├── services/       # deterministic code (no LLM)
    ├── rag/            # chunking, embeddings, retrieval
    ├── api/v1/         # compliance routers
    └── jobs/           # scheduled/background
```