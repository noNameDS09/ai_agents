"""License & Deadline Agent — tracks licensing, renewals, reporting deadlines."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentContract, AgentContext
from ..models.licensing import License
from ..models.tasks import RemediationTask
from ..services.rules_engine import (
    DeadlineRule,
    business_day_adjust,
    compute_deadline,
    compute_escalation_level,
)

logger = logging.getLogger("compliance.agents.license_deadline")


class LicenseDeadlineInput(BaseModel):
    org_id: str
    entity_id: Optional[str] = None
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None


class LicenseDeadlineOutput(BaseModel):
    upcoming_deadlines: list[dict] = Field(default_factory=list)
    tasks_created: int = 0
    overdue_count: int = 0
    escalated_count: int = 0


class LicenseDeadlineAgent(AgentContract):
    name = "license_deadline"
    input_schema = LicenseDeadlineInput
    output_schema = LicenseDeadlineOutput
    tool_allowlist = frozenset({"date_diff", "cron_describe", "current_time"})
    requires_approval = True
    max_retries = 2

    def __init__(self, rules: list[DeadlineRule] | None = None):
        self.rules = rules or []

    async def run(self, input_data: LicenseDeadlineInput, ctx: AgentContext) -> LicenseDeadlineOutput:
        session: AsyncSession = ctx.db_session
        org_id = input_data.org_id

        # Fetch licenses for this org/entity
        stmt = select(License).where(License.entity_id.isnot(None))
        if input_data.entity_id:
            stmt = stmt.where(License.entity_id == input_data.entity_id)
        result = await session.execute(stmt)
        licenses = result.scalars().all()

        upcoming = []
        tasks_created = 0
        overdue_count = 0
        escalated_count = 0

        now = date.today()

        for lic in licenses:
            if lic.expires_on is None:
                continue

            # Find matching rule
            rule = self._find_rule(lic)
            if rule is None:
                logger.warning("No rule found for license %s in jurisdiction %s", lic.id, lic.jurisdiction_id)
                continue

            deadline = compute_deadline(lic.expires_on, rule, now)
            deadline = business_day_adjust(deadline)

            days_until = (deadline - now).days
            if days_until < 0:
                overdue_count += 1

            # Determine escalation (days_until = days before deadline)
            escalation = compute_escalation_level(max(0, days_until), rule.escalation_ladder)
            if escalation > 0:
                escalated_count += 1

            upcoming.append({
                "license_id": str(lic.id),
                "license_type": lic.license_type,
                "expires_on": str(lic.expires_on),
                "deadline": str(deadline),
                "days_until_deadline": days_until,
                "escalation_level": escalation,
                "status": lic.status,
            })

            # Create remediation task if not already exists and within renewal window
            if days_until <= rule.renewal_window_days and days_until >= 0:
                task = RemediationTask(
                    org_id=org_id,
                    finding_id=None,
                    obligation_id=None,
                    title=f"Renew {lic.license_type} license (expires {lic.expires_on})",
                    description=f"License renewal due by {deadline}. Jurisdiction: {lic.jurisdiction_id}",
                    owner_user_id=None,
                    due_date=deadline,
                    escalation_level=escalation,
                    status="PENDING",
                )
                session.add(task)
                tasks_created += 1

        await session.flush()

        return LicenseDeadlineOutput(
            upcoming_deadlines=upcoming,
            tasks_created=tasks_created,
            overdue_count=overdue_count,
            escalated_count=escalated_count,
        )

    def _find_rule(self, license) -> Optional[DeadlineRule]:
        for rule in self.rules:
            if rule.jurisdiction_id == str(license.jurisdiction_id) and rule.license_type == license.license_type:
                return rule
        return None

    def validate_output(self, output: LicenseDeadlineOutput) -> list[str]:
        errors = []
        for dl in output.upcoming_deadlines:
            if dl.get("days_until_deadline", 0) < -365:
                errors.append(f"License {dl.get('license_id')} is over a year overdue")
        return errors