"""Regulation and obligation endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.organization import Jurisdiction
from ...models.regulatory import Obligation, RegulationVersion
from ...models.source import RegulatorySource
from ...services.rbac import (
    Principal,
    assert_org_access,
    require_action,
    set_rls_context,
)

router = APIRouter()


async def get_session():
    from agent_api.database import async_session
    async with async_session() as session:
        yield session


class SourceIngestRequest(BaseModel):
    jurisdiction_code: str
    source_url: str
    citation: str
    title: str
    publisher: Optional[str] = None
    publication_date: Optional[str] = None
    effective_date: Optional[str] = None
    source_type: str = "regulator_feed"
    prefer_tavily: bool = True


class ObligationMappingRequest(BaseModel):
    regulation_version_id: str
    org_id: str
    entity_ids: list[str] = []


class ObligationDecision(BaseModel):
    decision: str  # APPROVED | REJECTED
    rationale: str = ""


class SourceCreateRequest(BaseModel):
    jurisdiction_code: str
    name: str
    url: str
    source_type: str = "regulator_feed"
    fetch_interval_hours: int = 6


async def index_version_in_background(version_id: uuid.UUID) -> None:
    """Chunk + embed a regulation version using its own DB session.

    Background tasks outlive the request session, so they must not reuse it.
    Failures are recorded on the version (`index_status` / `index_error`) rather
    than lost; the scheduler retries PENDING/FAILED versions.
    """
    import logging

    from agent_api.database import async_session
    from ...services.ingest_pipeline import ingest_regulation_version

    logger = logging.getLogger("compliance.api.regulations")
    async with async_session() as session:
        try:
            result = await ingest_regulation_version(session, version_id)
            await session.commit()
            logger.info(
                "Indexed regulation version %s (%d chunks)", version_id, result.chunks_created
            )
        except Exception as exc:
            await session.commit()  # persist FAILED status set by the pipeline
            logger.error("Background indexing failed for %s: %s", version_id, exc)


@router.post("/regulations/ingest", status_code=status.HTTP_202_ACCEPTED)
async def ingest_regulation(
    body: SourceIngestRequest,
    background: BackgroundTasks,
    _principal: Principal = Depends(require_action("ingest_regulation")),
    session: AsyncSession = Depends(get_session),
):
    """Fetch a regulatory source, store a version, and index it in the background.

    Returns immediately with `index_status="PENDING"`. Poll
    `GET /regulations/{citation}/versions` until it becomes INDEXED or FAILED.
    """
    from ...agents.base import AgentContext
    from ...agents.regulatory_intelligence import RegulatoryIntelligenceAgent, RegulatoryIngestInput
    from agent_api.config import settings

    agent = RegulatoryIntelligenceAgent()
    input_data = RegulatoryIngestInput(
        jurisdiction_code=body.jurisdiction_code,
        source_url=body.source_url,
        citation=body.citation,
        title=body.title,
        publisher=body.publisher,
        publication_date=body.publication_date,
        effective_date=body.effective_date,
        source_type=body.source_type,
        prefer_tavily=body.prefer_tavily,
        tavily_api_key=settings.tavily_api_key,
        index=False,  # index in the background; free embedding tier is slow
    )
    ctx = AgentContext(
        org_id="",
        thread_id=f"regulatory-{uuid.uuid4()}",
        checkpoint_ns=f"regulatory:{uuid.uuid4()}",
        db_session=session,
    )
    try:
        result = await agent.run(input_data, ctx)
    except Exception as exc:
        # Do not leak internals; a source that cannot be fetched is an upstream
        # failure the caller can retry, not a bug in this service.
        import logging

        logging.getLogger("compliance.api.regulations").warning(
            "Regulatory ingest failed for %s: %s", body.source_url, exc
        )
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not fetch regulatory source: {type(exc).__name__}",
        ) from exc
    await session.commit()

    if result.regulation_version_id and result.changed:
        background.add_task(index_version_in_background, uuid.UUID(result.regulation_version_id))

    return result.model_dump()


@router.post("/regulations/versions/{version_id}/reindex", status_code=status.HTTP_202_ACCEPTED)
async def reindex_version(
    version_id: uuid.UUID,
    background: BackgroundTasks,
    _principal: Principal = Depends(require_action("ingest_regulation")),
    session: AsyncSession = Depends(get_session),
):
    """Re-run chunking + embedding for a regulation version.

    Intended for FAILED or PENDING versions (e.g. after an embedding outage).
    Safe to call on an INDEXED version: vectors are replaced, not duplicated.
    """
    version = await session.get(RegulationVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Regulation version not found")
    version.index_status = "PENDING"
    version.index_error = None
    await session.commit()
    background.add_task(index_version_in_background, version_id)
    return {"id": str(version_id), "index_status": "PENDING"}


@router.post("/sources", status_code=status.HTTP_201_CREATED)
async def create_source(
    body: SourceCreateRequest,
    _principal: Principal = Depends(require_action("ingest_regulation")),
    session: AsyncSession = Depends(get_session),
):
    """Register a regulatory source to monitor."""
    jur_result = await session.execute(
        select(Jurisdiction).where(Jurisdiction.code == body.jurisdiction_code)
    )
    jurisdiction = jur_result.scalar_one_or_none()
    if jurisdiction is None:
        raise HTTPException(status_code=404, detail="Jurisdiction not found")
    source = RegulatorySource(
        jurisdiction_id=jurisdiction.id,
        name=body.name,
        url=body.url,
        source_type=body.source_type,
        fetch_interval_hours=body.fetch_interval_hours,
    )
    session.add(source)
    await session.commit()
    await session.refresh(source)
    return {"id": str(source.id), "name": source.name, "url": source.url, "active": source.active}


@router.get("/sources")
async def list_sources(
    _principal: Principal = Depends(require_action("read_regulation")),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(RegulatorySource).order_by(RegulatorySource.created_at.desc()))
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "url": s.url,
            "source_type": s.source_type,
            "active": s.active,
            "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
        }
        for s in sources
    ]


@router.get("/regulations/{citation}/versions")
async def list_versions(
    citation: str,
    _principal: Principal = Depends(require_action("read_regulation")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(RegulationVersion).where(RegulationVersion.citation == citation).order_by(RegulationVersion.version_no.desc())
    result = await session.execute(stmt)
    versions = result.scalars().all()
    return [
        {
            "id": str(v.id),
            "citation": v.citation,
            "title": v.title,
            "version_no": v.version_no,
            "publication_date": str(v.publication_date) if v.publication_date else None,
            "effective_date": str(v.effective_date) if v.effective_date else None,
            "content_sha256": v.content_sha256,
            "supersedes_id": str(v.supersedes_id) if v.supersedes_id else None,
            "source_url": v.source_url,
            "index_status": v.index_status,
            "index_error": v.index_error,
            "index_collection": v.index_collection,
        }
        for v in versions
    ]


@router.get("/regulations/{citation}/versions/{version_no}")
async def get_version(
    citation: str,
    version_no: int,
    _principal: Principal = Depends(require_action("read_regulation")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(RegulationVersion).where(
        RegulationVersion.citation == citation,
        RegulationVersion.version_no == version_no,
    )
    result = await session.execute(stmt)
    v = result.scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return {
        "id": str(v.id),
        "citation": v.citation,
        "title": v.title,
        "version_no": v.version_no,
        "raw_text": v.raw_text,
        "source_url": v.source_url,
        "publisher": v.publisher,
        "publication_date": str(v.publication_date) if v.publication_date else None,
        "effective_date": str(v.effective_date) if v.effective_date else None,
    }


@router.post("/obligations/map", status_code=status.HTTP_202_ACCEPTED)
async def map_obligations(
    body: ObligationMappingRequest,
    principal: Principal = Depends(require_action("create_control")),
    session: AsyncSession = Depends(get_session),
):
    """Run the Obligation Mapping agent for a regulation version."""
    from ...agents.base import AgentContext
    from ...agents.obligation_mapping import ObligationMappingAgent, ObligationMappingInput

    assert_org_access(principal, body.org_id)
    await set_rls_context(session, body.org_id)

    agent = ObligationMappingAgent()
    input_data = ObligationMappingInput(
        regulation_version_id=body.regulation_version_id,
        org_id=body.org_id,
        entity_ids=body.entity_ids,
    )
    ctx = AgentContext(
        org_id=body.org_id,
        thread_id=f"obligation-{uuid.uuid4()}",
        checkpoint_ns=f"obligation:{uuid.uuid4()}",
        db_session=session,
    )
    result = await agent.run(input_data, ctx)
    await session.commit()
    return result.model_dump()


@router.get("/obligations")
async def list_obligations(
    org_id: Optional[str] = None,
    applicability: Optional[str] = None,
    principal: Principal = Depends(require_action("read_obligation")),
    session: AsyncSession = Depends(get_session),
):
    # Tenant-bound principals are always scoped to their own org; the query
    # parameter cannot widen access.
    if principal.is_cross_org:
        scope = uuid.UUID(org_id) if org_id else None
    else:
        scope = uuid.UUID(principal.org_id)
        if org_id and uuid.UUID(org_id) != scope:
            assert_org_access(principal, org_id)  # raises 403

    stmt = select(Obligation)
    if scope:
        # Scope the database session too (RLS), not just the query.
        await set_rls_context(session, scope)
        stmt = stmt.where(Obligation.org_id == scope)
    if applicability:
        stmt = stmt.where(Obligation.applicability == applicability)
    stmt = stmt.order_by(Obligation.created_at.desc())
    result = await session.execute(stmt)
    obligations = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "citation": o.citation,
            "normalized_text": o.normalized_text,
            "applicability": o.applicability,
            "status": o.status,
            "citation_chunk_ids": [str(c) for c in (o.citation_chunk_ids or [])],
            "approved_by": str(o.approved_by) if o.approved_by else None,
        }
        for o in obligations
    ]


@router.get("/obligations/review-queue")
async def review_queue(
    principal: Principal = Depends(require_action("approve_obligation")),
    session: AsyncSession = Depends(get_session),
):
    """List obligations pending review (POTENTIALLY_RELEVANT)."""
    stmt = select(Obligation).where(
        Obligation.applicability == "POTENTIALLY_RELEVANT",
        Obligation.status == "DRAFT",
    )
    if not principal.is_cross_org:
        await set_rls_context(session, principal.org_id)
        stmt = stmt.where(Obligation.org_id == uuid.UUID(principal.org_id))
    stmt = stmt.order_by(Obligation.created_at.desc())
    result = await session.execute(stmt)
    obligations = result.scalars().all()
    return [
        {
            "id": str(o.id),
            "citation": o.citation,
            "normalized_text": o.normalized_text,
            "citation_chunk_ids": [str(c) for c in (o.citation_chunk_ids or [])],
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in obligations
    ]


@router.post("/obligations/{obligation_id}/decide")
async def decide_obligation(
    obligation_id: uuid.UUID,
    body: ObligationDecision,
    principal: Principal = Depends(require_action("approve_obligation")),
    session: AsyncSession = Depends(get_session),
):
    """Approve (promote to CONFIRMED) or reject an obligation."""
    from datetime import datetime, timezone

    # Set the tenant context before loading so RLS can resolve the row.
    if principal.org_id:
        await set_rls_context(session, principal.org_id)
    obligation = await session.get(Obligation, obligation_id)
    if obligation is None:
        raise HTTPException(status_code=404, detail="Obligation not found")
    assert_org_access(principal, obligation.org_id)

    if body.decision == "APPROVED":
        obligation.applicability = "CONFIRMED"
        obligation.status = "ACTIVE"
        obligation.approved_at = datetime.now(timezone.utc)
    elif body.decision == "REJECTED":
        obligation.applicability = "NOT_APPLICABLE"
        obligation.status = "RETRACTED"
    else:
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    await session.commit()
    return {
        "id": str(obligation.id),
        "applicability": obligation.applicability,
        "status": obligation.status,
        "decision": body.decision,
        "rationale": body.rationale,
    }