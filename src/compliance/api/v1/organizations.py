"""Organization, entity, and jurisdiction endpoints."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.organization import Jurisdiction, LegalEntity, Organization
from ...services.rbac import require_role_dep

router = APIRouter()


async def get_session():
    from agent_api.database import async_session
    async with async_session() as session:
        yield session


class OrgCreate(BaseModel):
    legal_name: str
    industry: Optional[str] = None


class EntityCreate(BaseModel):
    name: str
    registration_no: Optional[str] = None
    country: str = "US"
    state: Optional[str] = None


@router.post("/organizations", status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrgCreate,
    _role: str = Depends(require_role_dep("create_organization")),
    session: AsyncSession = Depends(get_session),
):
    org = Organization(legal_name=body.legal_name, industry=body.industry)
    session.add(org)
    await session.commit()
    await session.refresh(org)
    return {"id": str(org.id), "legal_name": org.legal_name}


@router.get("/organizations/{org_id}")
async def get_organization(
    org_id: uuid.UUID,
    _role: str = Depends(require_role_dep("read_organization")),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return {"id": str(org.id), "legal_name": org.legal_name, "industry": org.industry}


@router.post("/organizations/{org_id}/entities", status_code=status.HTTP_201_CREATED)
async def create_entity(
    org_id: uuid.UUID,
    body: EntityCreate,
    _role: str = Depends(require_role_dep("create_entity")),
    session: AsyncSession = Depends(get_session),
):
    org = await session.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    entity = LegalEntity(
        org_id=org_id,
        name=body.name,
        registration_no=body.registration_no,
        country=body.country,
        state=body.state,
    )
    session.add(entity)
    await session.commit()
    await session.refresh(entity)
    return {"id": str(entity.id), "name": entity.name, "state": entity.state}


@router.get("/organizations/{org_id}/entities")
async def list_entities(
    org_id: uuid.UUID,
    _role: str = Depends(require_role_dep("read_entity")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(LegalEntity).where(LegalEntity.org_id == org_id)
    result = await session.execute(stmt)
    entities = result.scalars().all()
    return [{"id": str(e.id), "name": e.name, "state": e.state, "status": e.status} for e in entities]


@router.get("/jurisdictions")
async def list_jurisdictions(
    _role: str = Depends(require_role_dep("read_jurisdiction")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Jurisdiction).where(Jurisdiction.active == True)
    result = await session.execute(stmt)
    jurisdictions = result.scalars().all()
    return [{"id": str(j.id), "code": j.code, "name": j.name, "country": j.country, "regime": j.regime} for j in jurisdictions]