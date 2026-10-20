"""APScheduler-based job scheduler for compliance tasks.

Jobs:
- Regulatory source fetch (every 6 hours)
- Deadline reminder (daily 08:00 UTC)
- Escalation check (every hour)
- Audit chain verification (daily 00:00 UTC)
"""

from __future__ import annotations

import logging
import uuid
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

    # Re-index pending/failed regulation versions — every 15 minutes
    scheduler.add_job(
        _reindex_pending_versions,
        trigger=IntervalTrigger(minutes=15),
        id="reindex_pending_versions",
        name="Re-index pending regulation versions",
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
    from agent_api.config import settings
    from agent_api.database import async_session
    from sqlalchemy import select
    from ..models.source import RegulatorySource
    from ..agents.regulatory_intelligence import RegulatoryIntelligenceAgent, RegulatoryIngestInput
    from ..agents.base import AgentContext

    if not settings.tavily_api_key:
        logger.info("TAVILY_API_KEY not configured — skipping regulatory fetch")
        return

    async with async_session() as session:
        result = await session.execute(
            select(RegulatorySource).where(RegulatorySource.active == True)
        )
        sources = result.scalars().all()

        agent = RegulatoryIntelligenceAgent()
        for source in sources:
            try:
                input_data = RegulatoryIngestInput(
                    jurisdiction_code=await _jurisdiction_code(session, source.jurisdiction_id),
                    source_url=source.url,
                    citation=source.name,
                    title=source.name,
                    prefer_tavily=True,
                    tavily_api_key=settings.tavily_api_key,
                )
                ctx = AgentContext(
                    org_id="",
                    thread_id=f"fetch-{uuid.uuid4()}",
                    checkpoint_ns=f"fetch:{source.id}",
                    db_session=session,
                )
                result = await agent.run(input_data, ctx)
                logger.info("Fetched %s: changed=%s chunks=%s", source.url, result.changed, result.chunks_created)
            except Exception as exc:
                logger.warning("Failed to fetch source %s: %s", source.url, exc)
        await session.commit()


async def _jurisdiction_code(session, jurisdiction_id) -> str:
    from sqlalchemy import select
    from ..models.organization import Jurisdiction
    result = await session.execute(
        select(Jurisdiction.code).where(Jurisdiction.id == jurisdiction_id)
    )
    return result.scalar_one_or_none() or "US-FEDERAL"


async def _reindex_pending_versions() -> None:
    """Index regulation versions left PENDING or FAILED by an outage.

    Bounded per run so a large backlog cannot monopolize the worker; the job
    repeats every 15 minutes until the backlog drains.
    """
    from agent_api.database import async_session
    from sqlalchemy import or_, select
    from ..models.regulatory import RegulationVersion
    from ..services.ingest_pipeline import ingest_regulation_version
    from ..rag.retrieval import collection_name

    max_per_run = 5
    current_collection = collection_name()
    async with async_session() as session:
        result = await session.execute(
            select(RegulationVersion)
            .where(or_(
                RegulationVersion.index_status.in_(["PENDING", "FAILED"]),
                # Provider/model change: old vectors live in another collection
                # and would be invisible at retrieval time.
                RegulationVersion.index_collection.is_(None),
                RegulationVersion.index_collection != current_collection,
            ))
            .order_by(RegulationVersion.ingested_at.asc())
            .limit(max_per_run)
        )
        versions = result.scalars().all()
        if not versions:
            return

        logger.info("Re-indexing %d regulation version(s)", len(versions))
        for version in versions:
            try:
                outcome = await ingest_regulation_version(session, version.id)
                await session.commit()
                logger.info(
                    "Re-indexed %s (%d chunks)", version.id, outcome.chunks_created
                )
            except Exception as exc:
                await session.commit()  # keep FAILED status + error text
                logger.warning("Re-index failed for %s: %s", version.id, exc)


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
    from .services.audit_chain import verify_audit_chain
    from agent_api.database import async_session
    async with async_session() as session:
        result = await verify_audit_chain(session)
        if result["status"] != "ok":
            logger.error("Audit chain verification FAILED: %s", result)
            # Send alert notification
        else:
            logger.info("Audit chain verified: %d events checked", result["events_checked"])