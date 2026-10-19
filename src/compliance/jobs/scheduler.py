"""APScheduler-based job scheduler for compliance tasks.

Jobs:
- Regulatory source fetch (every 6 hours)
- Deadline reminder (daily 08:00 UTC)
- Escalation check (every hour)
- Audit chain verification (daily 00:00 UTC)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import compliance_settings

logger = logging.getLogger("compliance.jobs.scheduler")

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    """Start the APScheduler with all compliance jobs."""
    if not compliance_settings.apscheduler_enabled:
        logger.info("APScheduler disabled by config")
        return

    # Regulatory source fetch — every N hours
    scheduler.add_job(
        _fetch_regulations,
        trigger=IntervalTrigger(hours=compliance_settings.regulatory_fetch_interval_hours),
        id="fetch_regulations",
        name="Regulatory source fetch",
        replace_existing=True,
    )

    # Deadline reminder — daily at 08:00 UTC
    scheduler.add_job(
        _send_reminders,
        trigger=CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="send_reminders",
        name="Deadline reminder",
        replace_existing=True,
    )

    # Escalation check — every hour
    scheduler.add_job(
        _check_escalations,
        trigger=IntervalTrigger(hours=1),
        id="check_escalations",
        name="Escalation check",
        replace_existing=True,
    )

    # Audit chain verification — daily at 00:00 UTC
    scheduler.add_job(
        _verify_audit_chain,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        id="verify_audit_chain",
        name="Audit chain verification",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("APScheduler started with %d jobs", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")


async def _fetch_regulations() -> None:
    """Fetch regulatory updates from configured sources."""
    logger.info("Running regulatory source fetch")
    # TODO: Implement regulatory source fetch via Tavily MCP
    # 1. Load source registry from DB
    # 2. For each source, fetch latest content
    # 3. Hash and compare with stored version
    # 4. If changed, create new RegulationVersion
    # 5. Trigger Obligation Mapping agent for potentially affected obligations


async def _send_reminders() -> None:
    """Send deadline reminders for upcoming license renewals."""
    logger.info("Running deadline reminder check")
    # TODO: Implement deadline reminder
    # 1. Query licenses with expires_on within renewal window
    # 2. For each, check if reminder already sent
    # 3. Send notification via configured channels
    # 4. Log in audit_events


async def _check_escalations() -> None:
    """Check for overdue remediation tasks and escalate."""
    logger.info("Running escalation check")
    # TODO: Implement escalation check
    # 1. Query remediation_tasks with status PENDING/IN_PROGRESS and due_date < now
    # 2. For each overdue task, compute escalation level
    # 3. If escalation level increased, notify and update task
    # 4. Log in audit_events


async def _verify_audit_chain() -> None:
    """Verify audit chain integrity."""
    logger.info("Running audit chain verification")
    from .audit_chain import verify_audit_chain
    from agent_api.database import async_session
    async with async_session() as session:
        result = await verify_audit_chain(session)
        if result["status"] != "ok":
            logger.error("Audit chain verification FAILED: %s", result)
            # Send alert notification
        else:
            logger.info("Audit chain verified: %d events checked", result["events_checked"])