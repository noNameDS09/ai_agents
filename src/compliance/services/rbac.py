"""Authentication principal and RBAC dependencies for compliance endpoints.

Every request is resolved to a `Principal` (user, tenant, role). Endpoints that
touch tenant data must check the principal's org against the org they are
operating on — the org must come from the authenticated principal, never from
the request alone.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .permissions import ACTION_MIN_ROLE, parse_role, Role

logger = logging.getLogger("compliance.services.rbac")


@dataclass(frozen=True)
class Principal:
    """Authenticated caller.

    `org_id` is None only for the bootstrap/admin key, which is not bound to a
    tenant and may operate across orgs (used for onboarding and operations).
    """

    user_id: Optional[str]
    org_id: Optional[str]
    role: str

    @property
    def is_cross_org(self) -> bool:
        """True when this principal may act on any organization."""
        return self.org_id is None


def _hash_key(api_key: str) -> str:
    """Hash an API key for lookup/storage (keys are never stored in clear)."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


async def get_principal(request: Request) -> Principal:
    """Resolve the request's API key to a Principal.

    Raises 401 when the key is missing, unknown, or the user is inactive.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    # Bootstrap key from configuration: ops/admin, not tenant bound.
    from agent_api.config import settings
    if api_key == settings.api_key:
        return Principal(user_id=None, org_id=None, role="admin")

    from agent_api.database import async_session
    from ..models.user import User
    from sqlalchemy import text

    key_hash = _hash_key(api_key)
    async with async_session() as session:
        # Readable under RLS via the narrow `users_authenticate` policy, which
        # only exposes rows matching the presented key hash.
        await session.execute(
            text("SELECT set_config('app.auth_api_key_hash', :h, true)"),
            {"h": key_hash},
        )
        result = await session.execute(
            select(User).where(
                User.api_key_hash == key_hash,
                User.is_active == True,  # noqa: E712 - SQL comparison
            )
        )
        user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    return Principal(
        user_id=str(user.id),
        org_id=str(user.org_id) if user.org_id else None,
        role=user.role,
    )


def assert_org_access(principal: Principal, org_id: uuid.UUID | str) -> None:
    """Ensure the principal may act on `org_id`.

    Raises 403 when a tenant-bound principal targets a different organization.
    """
    if principal.is_cross_org:
        return
    if str(org_id) != principal.org_id:
        logger.warning(
            "Cross-tenant access blocked: user=%s org=%s requested=%s",
            principal.user_id, principal.org_id, org_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized for this organization",
        )


def require_action(action: str):
    """Dependency factory: resolve the principal and enforce the action's role.

    Returns the Principal so handlers can read the tenant scope.
    """
    async def _dep(principal: Principal = Depends(get_principal)) -> Principal:
        from .permissions import require_role as check_role
        check_role(principal.role, action)
        return principal
    return _dep


async def set_rls_context(session: AsyncSession, org_id: uuid.UUID | str) -> None:
    """Set the Postgres RLS tenant context for the current transaction.

    Defense-in-depth: even if a handler forgets a WHERE clause, the database
    refuses to return other tenants' rows — provided the app connects as a
    non-superuser role (see docs/SECURITY.md).

    Transaction-scoped (`set_config(..., true)`), so it can never leak into a
    later request that reuses the pooled connection.
    """
    from sqlalchemy import text

    await session.execute(
        text("SELECT set_config('app.current_org_id', :org_id, true)"),
        {"org_id": str(org_id)},
    )


# --------------------------------------------------------------------------
# Backwards-compatible role-only dependency
# --------------------------------------------------------------------------

# Legacy in-memory cache kept for compatibility with earlier callers.
_role_cache: dict[str, tuple[str, str]] = {}


def get_user_role_from_key(api_key: str) -> Optional[str]:
    """Look up a role from an API key (bootstrap key + legacy cache)."""
    from agent_api.config import settings
    if api_key == settings.api_key:
        return "admin"
    return _role_cache.get(_hash_key(api_key), (None, None))[1]


async def require_role(action: str, request: Request) -> str:
    """Role-only check, kept for compatibility. Prefer `require_action`."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    role = get_user_role_from_key(api_key)
    if role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    from .permissions import require_role as check_role
    check_role(role, action)

    return role


def require_role_dep(action: str):
    """Create a role-only dependency. Prefer `require_action` for new code."""
    async def _dep(request: Request) -> str:
        return await require_role(action, request)
    return _dep
