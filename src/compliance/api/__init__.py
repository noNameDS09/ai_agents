"""Compliance API layer."""

from fastapi import APIRouter

from .v1 import audit_router, licenses_router, organizations_router, workflows_router

router = APIRouter(prefix="/v1/compliance")
router.include_router(organizations_router)
router.include_router(licenses_router)
router.include_router(workflows_router)
router.include_router(audit_router)