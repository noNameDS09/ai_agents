"""License CRUD and deadline endpoints."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.licensing import License
from ...models.organization import LegalEntity
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


class LicenseCreate(BaseModel):
    license_type: str
    authority: str
    jurisdiction_id: uuid.UUID
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None
    renewal_window_days: int = 90


async def _load_entity_checked(
    session: AsyncSession,
    entity_id: uuid.UUID,
    principal: Principal,
) -> LegalEntity:
    """Load a legal entity and verify the principal may access its org.

    Raises 404 when missing (avoids leaking existence across tenants) and 403
    when the entity belongs to another organization.
    """
    # Under a non-superuser DB role, RLS hides rows until the tenant context is
    # set, so scope to the principal's org *before* the lookup.
    if principal.org_id:
        await set_rls_context(session, principal.org_id)
    entity = await session.get(LegalEntity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Legal entity not found")
    assert_org_access(principal, entity.org_id)
    await set_rls_context(session, entity.org_id)
    return entity


@router.post("/entities/{entity_id}/licenses", status_code=status.HTTP_201_CREATED)
async def create_license(
    entity_id: uuid.UUID,
    body: LicenseCreate,
    principal: Principal = Depends(require_action("create_license")),
    session: AsyncSession = Depends(get_session),
):
    entity = await _load_entity_checked(session, entity_id, principal)

    lic = License(
        entity_id=entity_id,
        license_type=body.license_type,
        authority=body.authority,
        jurisdiction_id=body.jurisdiction_id,
        issued_on=body.issued_on,
        expires_on=body.expires_on,
        renewal_window_days=body.renewal_window_days,
    )
    session.add(lic)
    await session.commit()
    await session.refresh(lic)
    return {"id": str(lic.id), "license_type": lic.license_type, "status": lic.status}


@router.get("/entities/{entity_id}/licenses")
async def list_licenses(
    entity_id: uuid.UUID,
    principal: Principal = Depends(require_action("read_license")),
    session: AsyncSession = Depends(get_session),
):
    await _load_entity_checked(session, entity_id, principal)
    stmt = select(License).where(License.entity_id == entity_id)
    result = await session.execute(stmt)
    licenses = result.scalars().all()
    return [
        {
            "id": str(lic.id),
            "license_type": lic.license_type,
            "authority": lic.authority,
            "expires_on": str(lic.expires_on) if lic.expires_on else None,
            "status": lic.status,
            "renewal_window_days": lic.renewal_window_days,
        }
        for lic in licenses
    ]


@router.get("/licenses/deadlines")
async def list_deadlines(
    days_ahead: int = Query(90, ge=1, le=365),
    principal: Principal = Depends(require_action("read_license")),
    session: AsyncSession = Depends(get_session),
):
    from datetime import date, timedelta
    cutoff = date.today() + timedelta(days=days_ahead)
    stmt = select(License).where(
        License.expires_on.isnot(None),
        License.expires_on <= cutoff,
    )
    # Tenant-bound principals only see licenses of entities in their own org.
    if not principal.is_cross_org:
        await set_rls_context(session, principal.org_id)
        stmt = stmt.where(
            License.entity_id.in_(
                select(LegalEntity.id).where(LegalEntity.org_id == uuid.UUID(principal.org_id))
            )
        )
    result = await session.execute(stmt)
    licenses = result.scalars().all()
    return [
        {
            "license_id": str(lic.id),
            "license_type": lic.license_type,
            "expires_on": str(lic.expires_on),
            "days_until_expiry": (lic.expires_on - date.today()).days,
            "status": lic.status,
        }
        for lic in licenses
    ]