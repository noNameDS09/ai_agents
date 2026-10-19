"""RBAC permission evaluation for compliance endpoints.

Roles (ordered by privilege):
  admin > compliance_officer > reviewer > auditor > viewer
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional

from fastapi import HTTPException, status


class Role(IntEnum):
    VIEWER = 0
    AUDITOR = 1
    REVIEWER = 2
    COMPLIANCE_OFFICER = 3
    ADMIN = 4


ROLE_HIERARCHY = {
    "viewer": Role.VIEWER,
    "auditor": Role.AUDITOR,
    "reviewer": Role.REVIEWER,
    "compliance_officer": Role.COMPLIANCE_OFFICER,
    "admin": Role.ADMIN,
}

# Minimum role required per action
ACTION_MIN_ROLE = {
    # Read
    "read_organization": Role.VIEWER,
    "read_entity": Role.VIEWER,
    "read_license": Role.VIEWER,
    "read_jurisdiction": Role.VIEWER,
    "read_regulation": Role.VIEWER,
    "read_obligation": Role.VIEWER,
    "read_control": Role.VIEWER,
    "read_finding": Role.VIEWER,
    "read_task": Role.VIEWER,
    "read_evidence": Role.VIEWER,
    "read_report": Role.VIEWER,
    "read_audit": Role.AUDITOR,
    # Write
    "create_organization": Role.ADMIN,
    "update_organization": Role.ADMIN,
    "create_entity": Role.COMPLIANCE_OFFICER,
    "create_license": Role.COMPLIANCE_OFFICER,
    "update_license": Role.COMPLIANCE_OFFICER,
    "ingest_regulation": Role.COMPLIANCE_OFFICER,
    "create_control": Role.COMPLIANCE_OFFICER,
    "assess_control": Role.COMPLIANCE_OFFICER,
    "acknowledge_finding": Role.COMPLIANCE_OFFICER,
    "remediate_finding": Role.COMPLIANCE_OFFICER,
    "update_task": Role.COMPLIANCE_OFFICER,
    "complete_task": Role.COMPLIANCE_OFFICER,
    "upload_evidence": Role.COMPLIANCE_OFFICER,
    "generate_report": Role.COMPLIANCE_OFFICER,
    "run_workflow": Role.COMPLIANCE_OFFICER,
    # Approval
    "approve_obligation": Role.REVIEWER,
    "reject_obligation": Role.REVIEWER,
    "decide_approval": Role.REVIEWER,
    "resume_workflow": Role.REVIEWER,
    # Admin
    "manage_users": Role.ADMIN,
    "manage_roles": Role.ADMIN,
}


def parse_role(role_str: str) -> Role:
    """Parse a role string into a Role enum. Raises ValueError for unknown roles."""
    r = ROLE_HIERARCHY.get(role_str.lower().strip())
    if r is None:
        raise ValueError(f"Unknown role: {role_str}")
    return r


def require_role(user_role: str, action: str) -> None:
    """Raise HTTPException(403) if the user's role is insufficient for the action."""
    user = parse_role(user_role)
    required = ACTION_MIN_ROLE.get(action)
    if required is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Unknown action: {action}",
        )
    if user < required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions: {user.name} < {required.name} required for {action}",
        )