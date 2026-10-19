"""RBAC dependency for FastAPI compliance endpoints.

Provides `require_role(action)` dependency that checks the user's role
against the minimum role required for the action.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .permissions import ACTION_MIN_ROLE, parse_role, Role

logger = logging.getLogger("compliance.services.rbac")

# In-memory cache: api_key_hash -> (user_id, role)
# In production, use Redis or a proper session store
_role_cache: dict[str, tuple[str, str]] = {}


def get_user_role_from_key(api_key: str) -> Optional[str]:
    """Look up the user's role from their API key.

    For Phase 0 MVP, we use a simple in-memory mapping.
    In production, this would query the users table.
    """
    # Default: the configured API_KEY maps to admin
    from agent_api.config import settings
    if api_key == settings.api_key:
        return "admin"
    return _role_cache.get(hashlib.sha256(api_key.encode()).hexdigest(), (None, None))[1]


async def require_role(action: str, request: Request) -> str:
    """FastAPI dependency: check RBAC for the given action.

    Raises HTTPException(401) if no API key, 403 if insufficient role.
    Returns the user's role string.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    role = get_user_role_from_key(api_key)
    if role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Check role hierarchy
    from .permissions import require_role as check_role
    check_role(role, action)

    return role


def require_role_dep(action: str):
    """Create a FastAPI dependency for a specific action."""
    async def _dep(request: Request) -> str:
        return await require_role(action, request)
    return _dep