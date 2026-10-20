"""Regulatory Intelligence Agent — collects regulations, detects amendments.

Fetches content from authoritative sources, stores versioned RegulationVersion
records, detects changes vs the previous version, and reports a summary with
citations. Ingest only — no approval required.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentContract, AgentContext
from ..models.organization import Jurisdiction
from ..models.regulatory import RegulationVersion
from ..models.source import RegulatorySource
from ..services.diffing import diff_texts
from ..services.source_fetching import fetch_source

logger = logging.getLogger("compliance.agents.regulatory_intelligence")


class RegulatoryIngestInput(BaseModel):
    jurisdiction_code: str
    source_url: str
    citation: str
    title: str
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    source_type: str = "regulator_feed"
    prefer_tavily: bool = True
    tavily_api_key: Optional[str] = None
    # Inline chunk+embed can take ~60s on free embedding tiers. API callers
    # set this False and index in the background; batch jobs leave it True.
    index: bool = True


class RegulatoryIngestOutput(BaseModel):
    regulation_version_id: Optional[str] = None
    changed: bool
    change_summary: str
    source_url: str
    content_sha256: str
    previous_sha256: Optional[str] = None
    version_no: int = 1
    chunks_created: int = 0
    index_status: str = "PENDING"
    index_error: Optional[str] = None
    citations: list[str] = Field(default_factory=list)


class RegulatoryIntelligenceAgent(AgentContract):
    name = "regulatory_intelligence"
    input_schema = RegulatoryIngestInput
    output_schema = RegulatoryIngestOutput
    tool_allowlist = frozenset({"web_search", "url_extract"})
    requires_approval = False
    max_retries = 2

    async def run(self, input_data: RegulatoryIngestInput, ctx: AgentContext) -> RegulatoryIngestOutput:
        session: AsyncSession = ctx.db_session

        # Find or create jurisdiction
        jur_result = await session.execute(
            select(Jurisdiction).where(Jurisdiction.code == input_data.jurisdiction_code)
        )
        jurisdiction = jur_result.scalar_one_or_none()
        if jurisdiction is None:
            jurisdiction = Jurisdiction(
                code=input_data.jurisdiction_code,
                name=input_data.jurisdiction_code,
                country="US",
                regime="money_transmitter",
            )
            session.add(jurisdiction)
            await session.flush()

        # Find or create the source record
        src_result = await session.execute(
            select(RegulatorySource).where(RegulatorySource.url == input_data.source_url)
        )
        source = src_result.scalar_one_or_none()
        if source is None:
            source = RegulatorySource(
                jurisdiction_id=jurisdiction.id,
                name=input_data.citation,
                url=input_data.source_url,
                source_type=input_data.source_type,
            )
            session.add(source)
            await session.flush()

        # Fetch content. The source hash is only a fetch hint; versioning is
        # decided per-citation below (see DATA-MODEL: uniqueness is
        # (citation, version_no)).
        fetched = await fetch_source(
            url=input_data.source_url,
            previous_sha256=source.last_content_sha256,
            prefer_tavily=input_data.prefer_tavily,
            tavily_api_key=input_data.tavily_api_key,
        )

        # Latest stored version for this citation, if any.
        last_version = await session.execute(
            select(RegulationVersion)
            .where(RegulationVersion.citation == input_data.citation)
            .order_by(RegulationVersion.version_no.desc())
            .limit(1)
        )
        prev = last_version.scalar_one_or_none()

        # A change is meaningful relative to the previous version of THIS
        # citation. A brand-new citation always creates version 1, even if the
        # same URL was already ingested under a different citation.
        changed = prev is None or fetched.content_sha256 != prev.content_sha256

        version_id = prev.id if prev else None
        version_no = prev.version_no if prev else 1
        chunks_created = 0
        index_status = prev.index_status if prev else "PENDING"
        index_error: Optional[str] = prev.index_error if prev else None
        previous_sha = prev.content_sha256 if prev else None

        if prev is None:
            change_summary = "Initial version (no previous content)."
        elif changed:
            change_summary = diff_texts(prev.raw_text, fetched.raw_text).summary
        else:
            change_summary = "No changes detected since the stored version."

        if changed:
            version_no = (prev.version_no + 1) if prev else 1

            rv = RegulationVersion(
                jurisdiction_id=jurisdiction.id,
                citation=input_data.citation,
                title=input_data.title,
                source_url=input_data.source_url,
                publisher=input_data.publisher,
                publication_date=date.fromisoformat(input_data.publication_date) if input_data.publication_date else None,
                effective_date=date.fromisoformat(input_data.effective_date) if input_data.effective_date else None,
                version_no=version_no,
                supersedes_id=prev.id if prev else None,
                raw_text=fetched.raw_text,
                content_sha256=fetched.content_sha256,
                index_status="PENDING",
                ingested_by=uuid.UUID(ctx.user_id) if ctx.user_id else None,
            )
            session.add(rv)
            await session.flush()
            version_id = rv.id
            index_status = "PENDING"
            index_error = None

            # Update source record
            source.last_content_sha256 = fetched.content_sha256
            source.last_fetched_at = datetime.now(timezone.utc)

            # Run ingest pipeline (chunk + embed + Qdrant). A failure here does
            # not invalidate the stored legal record — it marks the version as
            # FAILED so it can be re-indexed, and is reported to the caller.
            if input_data.index:
                try:
                    from ..services.ingest_pipeline import ingest_regulation_version
                    ingest_result = await ingest_regulation_version(session, version_id)
                    chunks_created = ingest_result.chunks_created
                    index_status = ingest_result.index_status
                except Exception as exc:
                    index_status = "FAILED"
                    index_error = str(exc)[:2000]
                    logger.error("Ingest pipeline failed for %s: %s", version_id, exc)
        else:
            # Still record that we checked the source.
            source.last_fetched_at = datetime.now(timezone.utc)

        await session.flush()

        return RegulatoryIngestOutput(
            regulation_version_id=str(version_id) if version_id else None,
            changed=changed,
            change_summary=change_summary,
            source_url=input_data.source_url,
            content_sha256=fetched.content_sha256,
            previous_sha256=previous_sha,
            version_no=version_no,
            chunks_created=chunks_created,
            index_status=index_status,
            index_error=index_error,
            citations=[input_data.source_url],
        )

    def validate_output(self, output: RegulatoryIngestOutput) -> list[str]:
        errors = []
        if output.changed and output.regulation_version_id is None:
            errors.append("Changed regulation should produce a regulation_version_id")
        if not output.source_url:
            errors.append("source_url is required")
        return errors