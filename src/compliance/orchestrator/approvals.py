"""Human-in-the-loop approval gates using LangGraph interrupt().

Provides the approval flow:
  1. Agent produces output requiring approval
  2. Orchestrator calls interrupt() with approval payload
  3. Graph pauses, checkpoint saved
  4. Human reviews via UI/API
  5. Human submits decision
  6. Orchestrator resumes graph with Command(resume=decision)
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from langgraph.types import Command, interrupt

from ..services.audit_chain import append_audit_event
from ..services.permissions import parse_role

logger = logging.getLogger("compliance.orchestrator.approvals")


async def request_approval(
    subject_type: str,
    subject_id: str,
    proposed_change: dict,
    agent_name: str,
    org_id: str,
    db_session: Any,
    user_id: Optional[str] = None,
) -> dict:
    """Request human approval via LangGraph interrupt().

    Returns the approval decision payload when resumed.
    """
    approval_payload = {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "proposed_change": proposed_change,
        "agent": agent_name,
        "org_id": org_id,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    # This pauses the graph and waits for human decision
    decision = interrupt(approval_payload)

    logger.info("Approval decision received: %s for %s/%s", decision, subject_type, subject_id)

    # Record the approval in the audit chain
    await append_audit_event(
        session=db_session,
        org_id=uuid.UUID(org_id),
        actor_type="USER" if user_id else "SYSTEM",
        actor_id=uuid.UUID(user_id) if user_id else uuid.uuid4(),
        event_type=f"{subject_type}.approval_decision",
        subject_type=subject_type,
        subject_id=uuid.UUID(subject_id),
        payload={
            "decision": decision.get("decision", "UNKNOWN"),
            "rationale": decision.get("rationale", ""),
            "agent": agent_name,
        },
    )

    return decision


def make_approval_node(agent_name: str, subject_type: str):
    """Create an approval node function for a given agent and subject type."""

    async def approval_node(state: dict) -> dict:
        output = state.get("output", {})
        subject_id = output.get("subject_id", "")
        org_id = state.get("ctx", {}).get("org_id", "")
        db_session = state.get("ctx", {}).get("db_session")

        decision = await request_approval(
            subject_type=subject_type,
            subject_id=subject_id,
            proposed_change=output,
            agent_name=agent_name,
            org_id=org_id,
            db_session=db_session,
        )

        return {
            "approval_decision": decision,
            "approved": decision.get("decision") == "APPROVED",
        }

    return approval_node