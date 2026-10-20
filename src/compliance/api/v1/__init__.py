"""Compliance v1 API routers."""

from .audit import router as audit_router
from .licenses import router as licenses_router
from .organizations import router as organizations_router
from .regulations import router as regulations_router
from .workflows import router as workflows_router

__all__ = [
    "audit_router",
    "licenses_router",
    "organizations_router",
    "regulations_router",
    "workflows_router",
]