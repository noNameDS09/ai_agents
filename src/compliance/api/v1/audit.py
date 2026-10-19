"""Audit verification endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...services.audit_chain import verify_audit_chain

router = APIRouter()


async def get_db_session():
    """Get a database session."""
    from agent_api.database import async_session
    async with async_session() as session:
        yield session


@router.get("/audit/verify")
async def verify_audit(request: Request, session: AsyncSession = Depends(get_db_session)):
    """Verify the audit chain integrity."""
    import uuid
    org_id = request.query_params.get("org_id")
    oid = uuid.UUID(org_id) if org_id else None
    result = await verify_audit_chain(session, oid)
    await session.commit()
    return result