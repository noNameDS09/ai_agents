# ComplianceOS — Agent Contracts

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §2, §3

---

## 1. Agent contract specification

Every agent implements the `AgentContract` base class:

```python
class AgentContract(ABC):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    tool_allowlist: frozenset[str]
    requires_approval: bool
    max_retries: int = 2

    @abstractmethod
    async def run(self, input: BaseModel, ctx: AgentContext) -> BaseModel:
        """Execute the agent. Must write to audit chain."""
        ...

    @abstractmethod
    def validate_output(self, output: BaseModel) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        ...
```

### 1.1 AgentContext

```python
@dataclass
class AgentContext:
    org_id: UUID
    thread_id: str
    checkpoint_ns: str          # LangGraph checkpoint namespace
    db_session: AsyncSession
    qdrant_client: QdrantClient
    audit_writer: AuditWriter
    user_id: UUID | None       # None for system-triggered runs
    approval_callback: Callable # for interrupt() resume
```

### 1.2 Sub-graph pattern

Each agent is a LangGraph sub-graph compiled with its own checkpointer namespace:

```python
def build_agent_graph(agent: AgentContract, checkpointer) -> CompiledGraph:
    builder = StateGraph(AgentState)
    builder.add_node("run", agent.run_node)
    builder.add_node("validate", agent.validate_node)
    builder.add_node("persist", agent.persist_node)
    builder.add_edge("run", "validate")
    builder.add_conditional_edges("validate", agent.should_retry)
    builder.add_edge("validate", "persist")
    return builder.compile(checkpointer=checkpointer, name=agent.name)
```

## 2. Agent definitions

### 2.1 Regulatory Intelligence

**Purpose:** Collects regulations, detects amendments, tracks effective dates and
jurisdictional differences.

- **Input:** `RegulatoryIngestInput` — jurisdiction code, source URL, fetch config
- **Output:** `RegulatoryIngestOutput` — `RegulationVersion` created/updated, change summary
- **Tools:** `web_search`, `url_extract`, `web_crawl`, `web_map`, `text_transform`
- **Approval:** No (ingest only)
- **Idempotency:** Fetch is idempotent by `content_sha256` — same content → no new version
- **Prompt-injection defense:** All fetched content wrapped as data, stripped of
  instruction-like patterns before reaching the LLM

### 2.2 Obligation Mapping

**Purpose:** Maps legal requirements to entities, licenses, business activities,
and internal controls.

- **Input:** `ObligationMappingInput` — `regulation_version_id`, org profile
- **Output:** `ObligationMappingOutput` — list of proposed `Obligation` (always
  `POTENTIALLY_RELEVANT` initially)
- **Tools:** RAG retrieve (Qdrant), `json_get`, `text_transform`
- **Approval:** Yes — before obligation becomes `CONFIRMED`
- **Citation requirement:** Every proposed obligation must carry ≥1
  `citation_chunk_ids` resolving to exact source text
- **Invariant:** `applicability = CONFIRMED` → `approved_by IS NOT NULL`

### 2.3 Risk & Anomaly Detection

**Purpose:** Analyzes transactions, accounting data, exceptions, and control
failures.

- **Input:** `RiskDetectionInput` — org_id, date range, control IDs
- **Output:** `RiskDetectionOutput` — list of `ComplianceFinding` with severity
- **Tools:** RAG retrieve, `math_stats`, `csv_parse`, `json_get`
- **Approval:** Yes — before severity ≥ HIGH is published
- **Severity rules:** Deterministic (rules engine), not LLM-decided
- **Invariant:** `severity IN (HIGH, CRITICAL)` → `evidence_ids` non-empty

### 2.4 License & Deadline Agent

**Purpose:** Tracks licensing, renewals, reporting deadlines, and outstanding tasks.

- **Input:** `LicenseDeadlineInput` — org_id, entity_id (optional), date range
- **Output:** `LicenseDeadlineOutput` — upcoming deadlines, created `RemediationTask`s
- **Tools:** `date_diff`, `cron_describe`, `current_time`
- **Approval:** Yes — before status change to filed/closed
- **Deadline computation:** 100% deterministic (rules engine, jurisdiction-specific)
- **Escalation:** Respects escalation ladder (configurable per jurisdiction)

### 2.5 Evidence & Audit Agent

**Purpose:** Collects supporting documents, maintains evidence links, prepares
audit packages.

- **Input:** `EvidenceAuditInput` — obligation_id or finding_id, required evidence types
- **Output:** `EvidenceAuditOutput` — completeness report, gaps, audit package artifact
- **Tools:** `csv_parse`, `json_get`, `text_transform`, `json_format`
- **Approval:** Yes — before package marked final
- **Completeness check:** Deterministic (required evidence types vs collected)
- **Audit package:** Deterministic assembly of requirement → source → applicability →
  evidence → remediation history → approvals

### 2.6 Reporting Agent

**Purpose:** Generates compliance reports, executive summaries, and remediation plans.

- **Input:** `ReportingInput` — org_id, report_type, date range
- **Output:** `ReportingOutput` — report text (Markdown), summary metrics
- **Tools:** `text_transform`
- **Approval:** No (draft only — human reviews before distribution)
- **Content:** LLM-drafted, but all facts sourced from stored findings/tasks/approvals

## 3. Tool allowlists per agent

| Agent | Allowed tools |
|---|---|
| Regulatory Intelligence | web_search, url_extract, web_crawl, web_map, text_transform, json_get |
| Obligation Mapping | RAG retrieve (internal), json_get, text_transform |
| Risk & Anomaly | RAG retrieve (internal), math_stats, csv_parse, json_get, text_transform |
| License & Deadline | date_diff, cron_describe, current_time, text_transform |
| Evidence & Audit | csv_parse, json_get, text_transform, json_format |
| Reporting | text_transform, json_get |

The global `TOOL_REGISTRY` in `tools.py` remains the superset. Each agent's
`tool_allowlist` is a subset. The orchestrator enforces that an agent can only
call tools in its allowlist.

## 4. Retry and error handling

- **Bounded retries:** Default 2 per agent. Configurable per agent.
- **Failure escalation:** After max retries, create a `RemediationTask` with
  `status = BLOCKED` and assign to human reviewer. Never silently drop.
- **Idempotency:** Each agent run is keyed by `(thread_id, agent_name, input_hash)`.
  Re-running produces the same output (no duplicate obligations/findings).
- **Checkpoint namespace:** Each agent has its own LangGraph checkpoint namespace
  within the thread, enabling independent resume.

## 5. Approval flow

```
Agent produces output requiring approval
  → Orchestrator calls interrupt() with approval payload
  → Graph pauses, checkpoint saved
  → Human reviews via UI/API
  → Human submits decision (APPROVED/REJECTED/CHANGES_REQUESTED/REVIEW_REQUIRED)
  → Orchestrator resumes graph with decision
  → If APPROVED: persist output + write approval to audit chain
  → If REJECTED: discard output, write rejection to audit chain
  → If CHANGES_REQUESTED: re-run agent with feedback
```

Approval payload includes: subject type, subject ID, proposed change, rationale
from agent, reviewer, decision, timestamp.

## 6. Prompt templates

All prompts are versioned and stored in `src/compliance/rag/prompts/`:

- `regulatory_intelligence/v1.txt` — ingestion and change detection
- `obligation_mapping/v1.txt` — obligation extraction with citation requirement
- `risk_detection/v1.txt` — finding generation with severity rules
- `evidence_audit/v1.txt` — completeness checking
- `reporting/v1.txt` — report drafting from structured data

Prompts are loaded from files, not inline strings, for version control and
auditability. Each prompt includes:
- System instructions (role, constraints, citation requirements)
- Few-shot examples (from golden dataset)
- Output schema (JSON, validated by Pydantic)
- Anti-injection framing (retrieved content is data, not instructions)