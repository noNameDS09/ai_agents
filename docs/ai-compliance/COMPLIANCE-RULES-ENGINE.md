# ComplianceOS — Rules Engine Specification

**Status:** Plan (pre-implementation)
**Source:** [AI-COMPLIANCE.md](../AI-COMPLIANCE.md) §4

---

## 1. Purpose

The rules engine is the **deterministic backbone** of ComplianceOS. It computes
deadlines, escalation levels, severity scores, and coverage assessments — never
via LLM. All rules are stored as **versioned data** (not code) so jurisdiction
changes can be audited and rolled back.

## 2. Rule types

### 2.1 Deadline rules

Each jurisdiction + license type has a rule defining:

| Field | Description |
|---|---|
| `jurisdiction_id` | FK → jurisdictions |
| `license_type` | e.g. "MTL", "lending", "broker_dealer" |
| `renewal_window_days` | Days before expiry when renewal can begin (e.g. 90) |
| `grace_period_days` | Days after expiry before suspension (e.g. 30) |
| `escalation_ladder` | List of (days_before_due, escalation_level, notification_channels) |
| `business_day_adjustment` | Whether deadlines shift to next business day |
| `effective_from` | Date rule becomes active |
| `effective_to` | Date rule expires (NULL = current) |

### 2.2 Severity rules

Deterministic severity assignment for compliance findings:

| Condition | Severity |
|---|---|
| License expired (past grace period) | CRITICAL |
| License expiring within 7 days | HIGH |
| License expiring within 30 days | MEDIUM |
| Control gap for HIGH-risk obligation | HIGH |
| Control gap for MEDIUM-risk obligation | MEDIUM |
| Missing evidence for HIGH severity finding | HIGH |
| Anomaly detected (transaction) | Based on amount threshold |
| Overdue remediation task (> 7 days) | HIGH |
| Overdue remediation task (1-7 days) | MEDIUM |

### 2.3 Coverage assessment rules

Control-to-obligation coverage is assessed as:

| Coverage | Criteria |
|---|---|
| FULL | Control directly addresses the obligation; evidence complete and current |
| PARTIAL | Control addresses the obligation but evidence is incomplete or stale |
| NONE | No control exists for this obligation |

### 2.4 Escalation ladder

```
Level 0: Email notification to task owner
Level 1: Email + Slack to owner + manager
Level 2: Email + Slack + SMS to owner + manager + compliance officer
Level 3: Email + Slack + SMS + phone call to compliance officer + executive
```

Escalation triggers:
- Task overdue by `days_before` threshold
- Severity upgraded (e.g., MEDIUM → HIGH)
- License status changed to EXPIRED

## 3. Deadline computation algorithm

```python
def compute_deadline(license, rule, now):
    """Deterministic deadline computation. No LLM involved."""
    expiry = license.expires_on
    renewal_start = expiry - timedelta(days=rule.renewal_window_days)

    if now < renewal_start:
        return renewal_start
    if now <= expiry:
        return expiry
    if now <= expiry + timedelta(days=rule.grace_period_days):
        return expiry + timedelta(days=rule.grace_period_days)
    return expiry + timedelta(days=rule.grace_period_days)

def business_day_adjust(date, jurisdiction):
    """Shift to next business day if jurisdiction requires it."""
    if not jurisdiction.business_day_adjustment:
        return date
    while date.weekday() >= 5:
        date += timedelta(days=1)
    while date in jurisdiction.holidays:
        date += timedelta(days=1)
    return date
```

## 4. Rules as data (versioning)

Rules are stored in a `jurisdiction_rules` table, not hardcoded. When a rule
changes, a new version is created with `effective_from = today` and the old
version's `effective_to` is set to yesterday. The rules engine always uses the
rule version where `effective_from <= now <= effective_to (or NULL)`.

## 5. State transitions

All state transitions are validated by the rules engine before execution:

```
License: ACTIVE → EXPIRING (when now >= expires_on - renewal_window_days)
License: EXPIRING → EXPIRED (when now > expires_on + grace_period_days)
License: EXPIRED → SUSPENDED (when now > expires_on + grace_period_days + 30)
License: * → ACTIVE (only via approval, status change to filed/closed)

Obligation: DRAFT → ACTIVE (requires approval)
Obligation: ACTIVE → SUPERSEDED (when regulation version superseded)
Obligation: * → RETRACTED (requires approval + rationale)

Finding: OPEN → ACKNOWLEDGED (compliance officer action)
Finding: ACKNOWLEDGED → REMEDIATED (task completed)
Finding: * → ACCEPTED (risk acceptance, requires approval)

Task: PENDING → IN_PROGRESS (owner starts work)
Task: IN_PROGRESS → BLOCKED (dependency blocked)
Task: * → DONE (completion, requires evidence)
Task: * → CANCELLED (requires approval + rationale)
```

## 6. Notification channels

| Channel | Use case | Implementation |
|---|---|---|
| Email | All notifications | SMTP / SendGrid |
| Slack | Escalation levels 1+ | Slack webhook |
| SMS | Escalation levels 2+ | Twilio |
| Phone | Escalation level 3 | Twilio voice |

Notification content is LLM-drafted but template-based, with deterministic
variable substitution (dates, license names, jurisdiction codes).