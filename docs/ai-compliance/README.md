# ComplianceOS — Documentation Index

**Status:** Phase 2 implemented (regulatory monitoring) — Phase 3 next
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md)

---

## What is ComplianceOS?

An autonomous compliance operations platform for companies operating across multiple
jurisdictions. Not a compliance chatbot — a system that executes compliance
operations with traceable evidence and controlled human approval.

See [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) for the full opportunity analysis.

## Documents

| Document | Contents |
|---|---|
| [COMPLIANCE-PLAN.md](COMPLIANCE-PLAN.md) | Master plan: phases, milestones, exit criteria, open questions, risks |
| [COMPLIANCE-ARCHITECTURE.md](COMPLIANCE-ARCHITECTURE.md) | System architecture, agent topology, data flow, tech stack |
| [COMPLIANCE-DATA-MODEL.md](COMPLIANCE-DATA-MODEL.md) | 12 entities, ER diagram, invariants, indexing, tenant isolation |
| [COMPLIANCE-TRUST-MODEL.md](COMPLIANCE-TRUST-MODEL.md) | Provenance, approvals, tamper-evidence, prompt-injection defense |
| [COMPLIANCE-AGENTS.md](COMPLIANCE-AGENTS.md) | Per-agent contracts, I/O schemas, tool allowlists, retry policy |
| [COMPLIANCE-API.md](COMPLIANCE-API.md) | REST API reference for compliance endpoints |
| [COMPLIANCE-RULES-ENGINE.md](COMPLIANCE-RULES-ENGINE.md) | Jurisdiction rules, deadline math, escalation ladders |
| [COMPLIANCE-EVALUATION.md](COMPLIANCE-EVALUATION.md) | Golden dataset, metrics, regression gates |
| [COMPLIANCE-RUNBOOK.md](COMPLIANCE-RUNBOOK.md) | Ops: setup, migrations, troubleshooting, incident response |

## Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| Embedding provider | Local sentence-transformers (all-MiniLM-L6-v2) | Free, private, no API key; OpenRouter has no embeddings |
| Vector store | Qdrant (self-hosted via Docker) | pgvector not available on this Postgres; purpose-built; keeps data on-server |
| MVP scope | US fintech license & deadline management | Narrow, measurable, directly addresses state-by-state licensing |
| Tenancy | Shared schema + RLS | Operational simplicity; RLS as defense-in-depth |
| Approval gates | LangGraph `interrupt()` | Parks graph; resumes on human decision |
| Audit trail | Hash-chained append-only | Tamper-evident; verifier endpoint |

## Phases

1. **Phase 0** — Foundations (pgvector/Qdrant, Alembic, tenancy, RBAC, audit chain, LangGraph upgrade)
2. **Phase 1** — MVP: License & deadline management
3. **Phase 2** — Regulatory change monitoring + RAG
4. **Phase 3** — Evidence, controls, audit packages
5. **Phase 4+** — Risk/anomaly, scale, integrations

## Relationship to `agent-api`

`agent-api` is **not** being replaced. It remains the generic, reusable agent
runtime. ComplianceOS is a **domain application built on top of it**, importing
`agent_api`'s infrastructure while adding its own domain models, agents,
orchestrator, and trust model.

See [COMPLIANCE-PLAN.md](COMPLIANCE-PLAN.md) for the full roadmap and immediate next steps.