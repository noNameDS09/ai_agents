"""Tenant-scoped repository layer.

Every query requires org_id. No implicit 'current org' lookup.
Postgres RLS policies provide defense-in-depth.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional, Sequence, TypeVar

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class TenantScopedRepository:
    """Base repository that enforces org_id scoping on all queries."""

    def __init__(self, session: AsyncSession, org_id: uuid.UUID):
        if not org_id:
            raise ValueError("org_id is required for tenant-scoped repository")
        self.session = session
        self.org_id = org_id

    async def set_rls_context(self) -> None:
        """Set the Postgres RLS context for this org (defense-in-depth).

        Uses SET LOCAL so the setting is scoped to the current transaction.
        Plain SET would persist on a pooled connection and could leak one
        tenant's context into a later request.
        """
        await self.session.execute(
            text("SELECT set_config('app.current_org_id', :org_id, true)"),
            {"org_id": str(self.org_id)},
        )

    async def get_by_id(self, model_class, entity_id: uuid.UUID):
        """Get a single entity by ID, scoped to org_id."""
        stmt = select(model_class).where(
            model_class.id == entity_id,
            model_class.org_id == self.org_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, model_class, limit: int = 100, offset: int = 0):
        """List all entities for this org."""
        stmt = (
            select(model_class)
            .where(model_class.org_id == self.org_id)
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def create(self, model_instance):
        """Create a new entity, ensuring org_id is set."""
        if hasattr(model_instance, "org_id") and model_instance.org_id is None:
            model_instance.org_id = self.org_id
        if getattr(model_instance, "org_id", None) != self.org_id:
            raise ValueError("Cannot create entity with different org_id")
        self.session.add(model_instance)
        await self.session.flush()
        return model_instance

    async def delete(self, model_class, entity_id: uuid.UUID) -> bool:
        """Delete an entity scoped to org_id. Returns True if deleted."""
        entity = await self.get_by_id(model_class, entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True