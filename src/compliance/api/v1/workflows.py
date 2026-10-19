"""Workflow trigger and status endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...services.rbac import require_role_dep

router = APIRouter()


class WorkflowRunRequest(BaseModel):
    workflow_type: str
    org_id: str
    entity_id: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None


async def get_session():
    from agent_api.database import async_session
    async with async_session() as session:
        yield session


@router.post("/workflows/run", status_code=status.HTTP_202_ACCEPTED)
async def run_workflow(
    req: WorkflowRunRequest,
    _role: str = Depends(require_role_dep("run_workflow")),
    session: AsyncSession = Depends(get_session),
):
    """Trigger a compliance workflow."""
    from ...agents.license_deadline import LicenseDeadlineAgent, LicenseDeadlineInput
    from ...services.rules_engine import DeadlineRule

    org_id = uuid.UUID(req.org_id)

    # Load rules (in production, from jurisdiction_rules table)
    rules = _default_rules()

    agent = LicenseDeadlineAgent(rules=rules)
    input_data = LicenseDeadlineInput(
        org_id=str(org_id),
        entity_id=req.entity_id,
        date_range_start=req.date_range_start,
        date_range_end=req.date_range_end,
    )

    from ...agents.base import AgentContext

    ctx = AgentContext(
        org_id=str(org_id),
        thread_id=f"compliance-{uuid.uuid4()}",
        checkpoint_ns=f"license_deadline:{org_id}",
        db_session=session,
    )

    result = await agent.run(input_data, ctx)
    await session.commit()

    return {
        "thread_id": ctx.thread_id,
        "status": "completed",
        "agents_invoked": [agent.name],
        "tasks_created": result.tasks_created,
        "overdue_count": result.overdue_count,
        "escalated_count": result.escalated_count,
        "upcoming_deadlines": result.upcoming_deadlines,
    }


@router.get("/workflows/{thread_id}")
async def get_workflow_status(thread_id: str):
    """Get workflow status (placeholder — returns running)."""
    return {"thread_id": thread_id, "status": "completed"}


def _default_rules():
    """Default deadline rules for MVP jurisdictions (CA, NY, TX)."""
    from ...services.rules_engine import DeadlineRule
    from datetime import date

    rules_data = [
        {
            "jurisdiction_id": "US-CA",
            "license_type": "MTL",
            "renewal_window_days": 90,
            "grace_period_days": 30,
            "escalation_ladder": [
                {"days_before": 60, "level": 0, "channels": ["email"]},
                {"days_before": 30, "level": 1, "channels": ["email", "slack"]},
                {"days_before": 14, "level": 2, "channels": ["email", "slack", "sms"]},
                {"days_before": 7, "level": 3, "channels": ["email", "slack", "sms", "phone"]},
            ],
            "business_day_adjustment": True,
            "effective_from": "2026-01-01",
            "effective_to": None,
        },
        {
            "jurisdiction_id": "US-NY",
            "license_type": "MTL",
            "renewal_window_days": 60,
            "grace_period_days": 15,
            "escalation_ladder": [
                {"days_before": 45, "level": 0, "channels": ["email"]},
                {"days_before": 30, "level": 1, "channels": ["email", "slack"]},
                {"days_before": 14, "level": 2, "channels": ["email", "slack", "sms"]},
                {"days_before": 7, "level": 3, "channels": ["email", "slack", "sms", "phone"]},
            ],
            "business_day_adjustment": False,
            "effective_from": "2026-01-01",
            "effective_to": None,
        },
        {
            "jurisdiction_id": "US-TX",
            "license_type": "MTL",
            "renewal_window_days": 60,
            "grace_period_days": 30,
            "escalation_ladder": [
                {"days_before": 45, "level": 0, "channels": ["email"]},
                {"days_before": 30, "level": 1, "channels": ["email", "slack"]},
                {"days_before": 14, "level": 2, "channels": ["email", "slack", "sms"]},
                {"days_before": 7, "level": 3, "channels": ["email", "slack", "sms", "phone"]},
            ],
            "business_day_adjustment": True,
            "effective_from": "2026-01-01",
            "effective_to": None,
        },
    ]
    return [DeadlineRule.from_dict(r) for r in rules_data]