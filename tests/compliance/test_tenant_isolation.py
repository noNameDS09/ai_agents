"""Tests for principal-based tenant isolation.

Pure unit tests — no database or network.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from compliance.services.rbac import Principal, assert_org_access


def _principal(org_id=None, role="admin"):
    return Principal(user_id="u-1", org_id=org_id, role=role)


def test_cross_org_principal_can_access_any_org():
    principal = _principal(org_id=None)
    assert principal.is_cross_org is True
    # Should not raise.
    assert_org_access(principal, uuid.uuid4())


def test_tenant_principal_can_access_own_org():
    org = uuid.uuid4()
    principal = _principal(org_id=str(org))
    assert_org_access(principal, org)  # should not raise


def test_tenant_principal_cannot_access_other_org():
    principal = _principal(org_id=str(uuid.uuid4()))
    with pytest.raises(HTTPException) as exc:
        assert_org_access(principal, uuid.uuid4())
    assert exc.value.status_code == 403


def test_tenant_principal_string_and_uuid_forms_match():
    org = uuid.uuid4()
    principal = _principal(org_id=str(org))
    assert_org_access(principal, str(org))
    assert_org_access(principal, org)
