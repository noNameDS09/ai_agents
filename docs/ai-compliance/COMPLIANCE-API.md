# ComplianceOS — API Reference

**Status:** Plan (pre-implementation)
**Base path:** `/v1/compliance`
**Auth:** `X-API-Key` + RBAC role check on every endpoint

---

## 1. Authentication

All compliance endpoints require:
1. Valid `X-API-Key` header (existing auth)
2. RBAC role check (new) — returns 403 if the user's role lacks permission

Roles: `admin`, `compliance_officer`, `reviewer`, `auditor`, `viewer`

## 2. Endpoints

### Organizations

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/organizations` | admin | Create organization |
| `GET` | `/organizations/{id}` | any | Get organization profile |
| `PUT` | `/organizations/{id}` | admin | Update organization |

### Legal entities

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/organizations/{org_id}/entities` | compliance_officer | Create legal entity |
| `GET` | `/organizations/{org_id}/entities` | any | List legal entities |
| `GET` | `/entities/{id}` | any | Get entity details |

### Licenses

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/entities/{entity_id}/licenses` | compliance_officer | Add license |
| `GET` | `/entities/{entity_id}/licenses` | any | List licenses |
| `GET` | `/licenses/{id}` | any | Get license details |
| `PUT` | `/licenses/{id}` | compliance_officer | Update license |
| `GET` | `/licenses/deadlines` | any | Upcoming renewal deadlines |
| `POST` | `/licenses/{id}/renew` | compliance_officer | Initiate renewal (triggers approval) |

### Jurisdictions

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/jurisdictions` | any | List jurisdictions |
| `GET` | `/jurisdictions/{code}` | any | Get jurisdiction details |

### Regulations

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/regulations/ingest` | compliance_officer | Ingest regulatory source |
| `GET` | `/regulations/{citation}/versions` | any | List versions |
| `GET` | `/regulations/{citation}/versions/{version_no}` | any | Get specific version |
| `GET` | `/regulations/{citation}/diff/{v1}/{v2}` | any | Diff two versions |

### Obligations

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/obligations` | any | List obligations (filter by org, status, applicability) |
| `GET` | `/obligations/{id}` | any | Get obligation with citations |
| `POST` | `/obligations/{id}/approve` | reviewer | Approve obligation (promotes to CONFIRMED) |
| `POST` | `/obligations/{id}/reject` | reviewer | Reject obligation |
| `GET` | `/obligations/review-queue` | reviewer | List pending review items |

### Controls

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/controls` | compliance_officer | Create control |
| `GET` | `/controls` | any | List controls |
| `POST` | `/controls/{id}/assess` | compliance_officer | Assess control coverage of an obligation |

### Findings

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/findings` | any | List findings (filter by severity, status) |
| `GET` | `/findings/{id}` | any | Get finding with evidence |
| `POST` | `/findings/{id}/acknowledge` | compliance_officer | Acknowledge finding |
| `POST` | `/findings/{id}/remediate` | compliance_officer | Mark remediated |

### Remediation tasks

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/tasks` | any | List tasks (filter by status, owner, due date) |
| `GET` | `/tasks/{id}` | any | Get task details |
| `PUT` | `/tasks/{id}` | compliance_officer | Update task status |
| `POST` | `/tasks/{id}/complete` | compliance_officer | Complete task |

### Evidence

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/evidence` | compliance_officer | Upload evidence |
| `GET` | `/evidence/{id}` | any | Get evidence details |
| `GET` | `/evidence/{id}/download` | any | Download evidence file |

### Approvals

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/approvals/pending` | reviewer | List pending approvals |
| `POST` | `/approvals/{id}/decide` | reviewer | Submit approval decision |

### Audit

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `GET` | `/audit/events` | auditor | List audit events (paginated) |
| `GET` | `/audit/verify` | auditor | Verify hash chain integrity |
| `GET` | `/audit/export` | auditor | Export audit log (JSON/CSV) |

### Reports

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/reports/generate` | compliance_officer | Generate audit package |
| `GET` | `/reports/{id}` | any | Get report details |
| `GET` | `/reports/{id}/download` | any | Download report (PDF/JSON) |

### Workflows

| Method | Path | Role | Description |
|--------|------|------|-------------|
| `POST` | `/workflows/run` | compliance_officer | Trigger a compliance workflow |
| `GET` | `/workflows/{thread_id}` | any | Get workflow status |
| `POST` | `/workflows/{thread_id}/resume` | reviewer | Resume paused workflow (after approval) |

## 3. Request/response examples

### POST /v1/compliance/workflows/run

**Request:**
```json
{
  "workflow_type": "license_deadline_check",
  "org_id": "uuid",
  "entity_id": "uuid (optional)",
  "date_range": {"start": "2026-01-01", "end": "2026-03-31"}
}
```

**Response:**
```json
{
  "thread_id": "uuid",
  "status": "running",
  "agents_invoked": ["license_deadline"],
  "tasks_created": 3,
  "findings": []
}
```

### POST /v1/compliance/obligations/{id}/approve

**Request:**
```json
{
  "decision": "APPROVED",
  "rationale": "Confirmed against CFPB Reg Z 1026.17 source text"
}
```

**Response:**
```json
{
  "obligation_id": "uuid",
  "applicability": "CONFIRMED",
  "approved_by": "user-uuid",
  "approved_at": "2026-10-19T12:00:00Z",
  "approval_hash": "sha256:..."
}
```

## 4. Error responses

| Status | Meaning |
|--------|---------|
| `401` | Missing or invalid API key |
| `403` | Insufficient RBAC role |
| `404` | Resource not found |
| `409` | Conflict (e.g., duplicate obligation) |
| `422` | Validation error |
| `429` | Rate limit exceeded |
| `503` | Inference not configured |