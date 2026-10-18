# ComplianceOS — Data Model

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §5

---

## 1. Entity overview

Twelve core entities. Relationships matter more than agent count — one regulation
creates many obligations; one obligation is satisfied by many controls; one control
supports obligations across many jurisdictions.

## 2. Entity definitions

### Organization
Company profile and business activities. Top-level tenant boundary.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `legal_name` | TEXT | |
| `industry` | TEXT | SIC/NAICS code |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

### LegalEntity
Subsidiaries and registered entities within an organization.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `name` | TEXT | |
| `registration_no` | TEXT | State registration number |
| `country` | TEXT | ISO 3166 |
| `state` | TEXT | US state code |
| `status` | ENUM | ACTIVE, INACTIVE, DISSOLVED |

### Jurisdiction
Countries, states, and regulatory regimes.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `code` | TEXT UNIQUE | e.g. "US-CA", "US-NY" |
| `name` | TEXT | |
| `country` | TEXT | ISO 3166 |
| `regime` | TEXT | e.g. "money_transmitter", "lending" |
| `regulator_url` | TEXT | Official regulator website |
| `active` | BOOLEAN | |

### License
License status, conditions, expiry, renewal.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `entity_id` | UUID FK → legal_entities | |
| `license_type` | TEXT | e.g. "MTL", "FinCEN MSB", "lending" |
| `authority` | TEXT | Issuing body |
| `jurisdiction_id` | UUID FK → jurisdictions | |
| `issued_on` | DATE | |
| `expires_on` | DATE | |
| `status` | ENUM | ACTIVE, EXPIRING, EXPIRED, SUSPENDED, REVOKED, PENDING_RENEWAL |
| `renewal_window_days` | INTEGER | Days before expiry when renewal can start |
| `document_id` | UUID FK → evidence | License document |

### RegulationVersion
Versioned source documents and amendments. **Immutable** once ingested.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `jurisdiction_id` | UUID FK → jurisdictions | |
| `citation` | TEXT | e.g. "CFPB Reg Z 1026.17" |
| `title` | TEXT | |
| `source_url` | TEXT | Official source URL |
| `publisher` | TEXT | Regulator name |
| `publication_date` | DATE | |
| `effective_date` | DATE | |
| `version_no` | INTEGER | Monotonically increasing |
| `supersedes_id` | UUID FK → regulation_versions | NULL for first version |
| `raw_text` | TEXT | Full regulatory text |
| `content_sha256` | TEXT | Content hash for dedup |
| `ingested_at` | TIMESTAMPTZ | |
| `ingested_by` | UUID FK → users | |
| UNIQUE | (citation, version_no) | |

### RegulationChunk
Chunks of a regulation version for RAG retrieval.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `regulation_version_id` | UUID FK → regulation_versions | |
| `chunk_index` | INTEGER | Order within version |
| `text` | TEXT | Chunk text |
| `token_count` | INTEGER | |
| `embedding` | vector(384) | Qdrant |
| `page_ref` | TEXT | Page/section reference |
| `char_start` | INTEGER | Character offset in raw_text |

### Obligation
Normalized requirement and applicability decision.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `regulation_version_id` | UUID FK → regulation_versions | |
| `citation` | TEXT | Short citation |
| `normalized_text` | TEXT | LLM-extracted obligation text |
| `applicability` | ENUM | POTENTIALLY_RELEVANT, CONFIRMED, NOT_APPLICABLE |
| `status` | ENUM | DRAFT, ACTIVE, SUPERSEDED, RETRACTED |
| `responsible_entity_id` | UUID FK → legal_entities | |
| `citation_chunk_ids` | UUID[] | Chunks supporting this obligation |
| `created_by` | UUID FK → users | |
| `created_at` | TIMESTAMPTZ | |
| `approved_by` | UUID FK → users | NULL until approved |
| `approved_at` | TIMESTAMPTZ | NULL until approved |

**Invariant:** `applicability = CONFIRMED` → `citation_chunk_ids IS NOT NULL` AND `approved_by IS NOT NULL`.

### Control
Internal procedure intended to satisfy an obligation.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `name` | TEXT | |
| `description` | TEXT | |
| `control_type` | TEXT | Preventive, Detective, Corrective |
| `frequency` | TEXT | Daily, Weekly, Monthly, Quarterly, Annual |
| `owner_entity_id` | UUID FK → legal_entities | |
| `status` | ENUM | ACTIVE, INACTIVE, UNDER_REVIEW |
| `created_at` | TIMESTAMPTZ | |

### ControlObligation
Coverage assessment linking controls to obligations.

| Field | Type | Notes |
|---|---|---|
| `control_id` | UUID FK → controls | |
| `obligation_id` | UUID FK → obligations | |
| `coverage` | ENUM | FULL, PARTIAL, NONE |
| `assessed_by` | UUID FK → users | |
| `assessed_at` | TIMESTAMPTZ | |
| `evidence_ids` | UUID[] | Supporting evidence |

### ComplianceFinding
Gap, anomaly, severity, and supporting evidence.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `obligation_id` | UUID FK → obligations | |
| `control_id` | UUID FK → controls | |
| `finding_type` | ENUM | GAP, ANOMALY, CONTROL_FAILURE, EXPIRY |
| `severity` | ENUM | LOW, MEDIUM, HIGH, CRITICAL |
| `description` | TEXT | |
| `status` | ENUM | OPEN, ACKNOWLEDGED, REMEDIATED, ACCEPTED |
| `evidence_ids` | UUID[] | |
| `detected_at` | TIMESTAMPTZ | |
| `resolved_at` | TIMESTAMPTZ | |

**Invariant:** `severity IN (HIGH, CRITICAL)` → `evidence_ids IS NOT NULL AND length(evidence_ids) > 0`.

### RemediationTask
Owner, deadline, status, and resolution.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `finding_id` | UUID FK → compliance_findings | |
| `obligation_id` | UUID FK → obligations | |
| `title` | TEXT | |
| `description` | TEXT | |
| `owner_user_id` | UUID FK → users | |
| `due_date` | DATE | Computed by rules engine |
| `escalation_level` | INTEGER | 0 = none, 1+ = escalated |
| `status` | ENUM | PENDING, IN_PROGRESS, BLOCKED, DONE, CANCELLED |
| `completed_at` | TIMESTAMPTZ | |
| `resolution_note` | TEXT | |

### Approval
Reviewer, decision, timestamp, and rationale.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `subject_type` | TEXT | "obligation", "finding", "task", "package" |
| `subject_id` | UUID | |
| `decision` | ENUM | APPROVED, REJECTED, CHANGES_REQUESTED, REVIEW_REQUIRED |
| `reviewer_user_id` | UUID FK → users | |
| `rationale` | TEXT | Required for REJECTED and CHANGES_REQUESTED |
| `decided_at` | TIMESTAMPTZ | |
| `previous_approval_hash` | TEXT | Hash chain link |
| `approval_hash` | TEXT | Hash of this approval |

### AuditEvent
Append-only history of actions and decisions.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `actor_type` | ENUM | AGENT, USER, SYSTEM |
| `actor_id` | UUID | |
| `event_type` | TEXT | e.g. "obligation.approved", "finding.created" |
| `subject_type` | TEXT | |
| `subject_id` | UUID | |
| `payload` | JSONB | Full event data |
| `prev_event_hash` | TEXT | Hash of previous event |
| `event_sha256` | TEXT | Hash of (prev_event_hash + payload) |
| `occurred_at` | TIMESTAMPTZ | |
| `seq` | BIGSERIAL | Monotonic sequence number |

**Invariant:** Append-only. UPDATE and DELETE revoked from application role.
Hash chain: `event_sha256 = SHA256(prev_event_hash || canonical_json(payload))`.

### Evidence
Documents, transactions, attestations, and source references.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations | Tenant scope |
| `kind` | ENUM | DOCUMENT, TRANSACTION, ATTESTATION, SOURCE_REFERENCE |
| `filename` | TEXT | |
| `storage_uri` | TEXT | S3/FS path |
| `content_sha256` | TEXT | Content hash for dedup + tamper detection |
| `mime_type` | TEXT | |
| `size_bytes` | BIGINT | |
| `uploaded_by` | UUID FK → users | |
| `collected_at` | TIMESTAMPTZ | |

## 3. Migrations policy

- **Alembic** replaces `init_db()` create-all from Phase 0.2.
- Every schema change is a migration with up/down scripts.
- Migrations run in CI before tests (no manual `CREATE TABLE`).
- Seed data (jurisdictions, license types) loaded via migration data scripts.
- `downgrade()` must be tested for every migration.

## 4. Indexing strategy

| Table | Index | Purpose |
|---|---|---|
| `regulation_chunks` | HNSW on `embedding` (Qdrant) | Semantic search |
| `regulation_chunks` | B-tree on `regulation_version_id` | Chunk lookup by version |
| `obligations` | B-tree on `org_id`, `status`, `applicability` | Filtered listing |
| `compliance_findings` | B-tree on `org_id`, `severity`, `status` | Dashboard queries |
| `remediation_tasks` | B-tree on `org_id`, `status`, `due_date` | Deadline sorting |
| `audit_events` | B-tree on `org_id`, `occurred_at`, `seq` | Chronological audit |
| `licenses` | B-tree on `entity_id`, `status`, `expires_on` | Expiry queries |

## 5. Tenant isolation

- Every table carries `org_id` (except `jurisdictions` and `regulation_versions`
  which are global reference data).
- Repository layer requires `org_id` as a mandatory parameter — no implicit
  "current org" lookup.
- Postgres RLS policies on all tenant-scoped tables as defense-in-depth.
- Qdrant collections are partitioned by `org_id` payload filter.
- Integration tests attempt cross-tenant reads and assert they fail.