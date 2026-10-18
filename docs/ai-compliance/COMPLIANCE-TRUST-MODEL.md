# ComplianceOS — Trust & Safety Model

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §7

---

## 1. Core principle

Financial compliance software must be designed around **verifiability, not just agent
autonomy**. Every result must be traceable, every workflow stateful, and every
consequential action permission-controlled.

## 2. Source provenance

Every regulatory finding must link to the authoritative source and its version.

- `obligation.regulation_version_id` → `regulation_versions` (versioned document)
- `obligation.citation_chunk_ids` → `regulation_chunks` (exact text passages)
- Citation renders to: source URL, publisher, publication date, effective date,
  version number, and the exact quoted text from the chunk.
- No finding, obligation, or report may be created without a resolvable citation.

## 3. No unsupported conclusions

- Applicability defaults to `POTENTIALLY_RELEVANT` — never `CONFIRMED`.
- Only a recorded human approval can promote to `CONFIRMED`.
- Uncertain cases are marked `REVIEW_REQUIRED` and routed to a human queue.
- The LLM is never allowed to declare an obligation "settled law" without
  citation + approval.

## 4. Human approval

LangGraph `interrupt()` gates before:

| Action | Gate | Approval stored |
|---|---|---|
| Obligation activation | Yes | reviewer, rationale, timestamp |
| High/critical finding publication | Yes | reviewer, rationale, timestamp |
| License status change | Yes | reviewer, rationale, timestamp |
| Audit package finalization | Yes | reviewer, rationale, timestamp |
| Remediation task cancellation | Yes | reviewer, rationale, timestamp |

Approval records include `previous_approval_hash` → `approval_hash` for
tamper-evidence.

## 5. Tenant isolation

- Every table carries `org_id` (except `jurisdictions` and `regulation_versions`
  which are global reference data).
- Repository layer requires `org_id` as a mandatory parameter — no implicit
  "current org" lookup.
- Postgres RLS policies on all tenant-scoped tables as defense-in-depth.
- Qdrant collections are partitioned by `org_id` payload filter.
- Integration tests attempt cross-tenant reads and assert they fail.

## 6. Tamper-evident audit trail

- `audit_events` is **append-only**: UPDATE and DELETE revoked from the
  application role.
- Hash chain: `event_sha256 = SHA256(prev_event_hash || canonical_json(payload))`.
- `GET /v1/audit/verify` re-walks the chain and reports the first break with
  the sequence number and timestamp.
- Every event records: actor type, actor ID, event type, subject type/ID,
  payload, timestamp, sequence number.

## 7. Prompt-injection defense

- Downloaded regulatory text and uploaded evidence are wrapped as **data**, never
  as instructions.
- Tool outputs from `url_extract`/`web_search` are fenced and stripped of
  instruction-like content before reaching the LLM.
- The LLM never receives raw HTML — only extracted, sanitized text.
- System prompt explicitly instructs the LLM to treat all retrieved content as
  untrusted data.
- Input validation on all tool arguments (Pydantic schemas).

## 8. Deterministic escape hatch

Calculations, permissions, deadline enforcement, validation, and workflow
transitions run in Python — never `eval`, never LLM-parsed.

| Operation | Deterministic? | Who runs it |
|---|---|---|
| Deadline calculation | Yes | Rules engine (Python) |
| Escalation ladder | Yes | Rules engine (Python) |
| Permission check | Yes | RBAC service (Python) |
| State transition validation | Yes | Orchestrator (Python) |
| Severity assignment | Yes | Rules engine (Python) |
| Obligation extraction | No (LLM) | Obligation Mapping agent |
| Evidence matching | No (LLM) | Evidence & Audit agent |
| Report drafting | No (LLM) | Reporting agent |

## 9. Evaluation

Test extraction accuracy, missed obligations, false alerts, citation correctness,
and whether regulatory changes are detected in time.

| Metric | Target | Measured by |
|---|---|---|
| Obligation extraction precision | ≥ 0.90 | Golden dataset |
| Obligation extraction recall | ≥ 0.85 | Golden dataset |
| Citation correctness | 100% | Every citation resolves to exact source text |
| False-positive rate | < 10% | Reviewed obligations vs confirmed |
| Time-to-detect | < 24h | `regulation_versions.ingested_at − publication_date` |
| Missed renewal rate | 0% | Simulated 90-day run |

Golden dataset: hand-curated (regulation → expected obligations) maintained in
`tests/compliance/golden/`. Runs in CI as a regression gate.