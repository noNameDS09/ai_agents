"""Hash-chained append-only audit event service.

Provides append() and verify() operations for the audit_events table.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import AuditEvent

logger = logging.getLogger("compliance.services.audit_chain")


def _canonical_json(payload: dict) -> str:
    """Deterministic JSON serialization for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(prev_hash: Optional[str], payload: dict) -> str:
    """Compute the SHA256 hash for an audit event."""
    data = (prev_hash or "") + _canonical_json(payload)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


async def append_audit_event(
    session: AsyncSession,
    org_id: uuid.UUID,
    actor_type: str,
    actor_id: uuid.UUID,
    event_type: str,
    subject_type: str,
    subject_id: uuid.UUID,
    payload: dict,
) -> AuditEvent:
    """Append a new audit event with hash chaining.

    The prev_event_hash is looked up from the most recent event for this org.
    """
    # Get the last event hash for this org
    stmt = (
        select(AuditEvent.event_sha256)
        .where(AuditEvent.org_id == org_id)
        .order_by(AuditEvent.seq.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    prev_hash = result.scalar_one_or_none()

    event_hash = compute_event_hash(prev_hash, payload)

    event = AuditEvent(
        org_id=org_id,
        actor_type=actor_type,
        actor_id=actor_id,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload,
        prev_event_hash=prev_hash,
        event_sha256=event_hash,
    )
    session.add(event)
    await session.flush()
    logger.info("Audit event appended: %s (seq=%s)", event_type, event.seq)
    return event


async def verify_audit_chain(
    session: AsyncSession,
    org_id: Optional[uuid.UUID] = None,
) -> dict:
    """Verify the audit chain integrity.

    Re-walks all events in sequence order and checks that each event's hash
    matches the computed hash from the previous event's hash + payload.

    Returns:
        {"status": "ok", "events_checked": N, "first_break": None}
        or {"status": "broken", "events_checked": N, "first_break": {...}}
    """
    stmt = select(AuditEvent).order_by(AuditEvent.seq.asc())
    if org_id:
        stmt = stmt.where(AuditEvent.org_id == org_id)

    result = await session.execute(stmt)
    events = result.scalars().all()

    if not events:
        return {"status": "ok", "events_checked": 0, "first_break": None}

    checked = 0
    for i, event in enumerate(events):
        expected_hash = compute_event_hash(event.prev_event_hash, event.payload)
        if expected_hash != event.event_sha256:
            return {
                "status": "broken",
                "events_checked": checked,
                "first_break": {
                    "seq": event.seq,
                    "event_id": str(event.id),
                    "occurred_at": event.occurred_at.isoformat(),
                    "expected_hash": expected_hash,
                    "actual_hash": event.event_sha256,
                },
            }
        # Check chain continuity
        if i > 0 and event.prev_event_hash != events[i - 1].event_sha256:
            return {
                "status": "broken",
                "events_checked": checked,
                "first_break": {
                    "seq": event.seq,
                    "event_id": str(event.id),
                    "occurred_at": event.occurred_at.isoformat(),
                    "reason": "chain discontinuity: prev_event_hash mismatch",
                },
            }
        checked += 1

    return {"status": "ok", "events_checked": checked, "first_break": None}