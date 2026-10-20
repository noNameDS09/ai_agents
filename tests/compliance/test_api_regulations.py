"""API integration tests for Phase 2 endpoints and tenant isolation.

Creates the compliance schema in the test database (idempotent) and exercises
the ASGI app with the configured test API key.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import create_async_engine

import compliance.models  # noqa: F401 - registers all tables on ComplianceBase
from compliance.models.base import ComplianceBase
from compliance.models.organization import Jurisdiction, Organization
from compliance.models.source import RegulatorySource
from compliance.models.user import User

API_KEY_HEADERS = {"X-API-Key": "test-api-key"}


@pytest.fixture(autouse=True)
async def _dispose_global_engine():
    """Release pooled connections between tests.

    `agent_api.database.engine` is module-level; pytest-asyncio gives each test
    its own event loop, so connections created in one loop must not be reused in
    the next (raises "Event loop is closed").
    """
    yield
    from agent_api.database import engine

    await engine.dispose()


@pytest.fixture(autouse=True)
async def _compliance_schema():
    """Ensure compliance tables exist in the test database.

    Function-scoped (with NullPool) because pytest-asyncio runs each test on its
    own event loop; a session-scoped async engine would leak connections across
    loops. `create_all` is idempotent.
    """
    from sqlalchemy.pool import NullPool

    from agent_api.config import settings

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(ComplianceBase.metadata.create_all)
    await engine.dispose()
    yield


@pytest.fixture
async def session():
    from agent_api.database import async_session

    async with async_session() as s:
        yield s


@pytest.fixture
async def jurisdiction(session):
    code = f"TS-{uuid.uuid4().hex[:6].upper()}"
    jur = Jurisdiction(code=code, name="Test State", country="US", regime="money_transmitter")
    session.add(jur)
    await session.commit()
    await session.refresh(jur)
    yield jur
    await session.execute(delete(RegulatorySource).where(RegulatorySource.jurisdiction_id == jur.id))
    await session.execute(delete(Jurisdiction).where(Jurisdiction.id == jur.id))
    await session.commit()


async def test_create_and_list_regulatory_source(client, jurisdiction):
    payload = {
        "jurisdiction_code": jurisdiction.code,
        "name": "Test Regulator Feed",
        "url": f"https://example.test/{uuid.uuid4().hex}/statute",
        "source_type": "regulator_feed",
    }
    res = await client.post("/v1/compliance/sources", json=payload, headers=API_KEY_HEADERS)
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["name"] == payload["name"]
    assert created["active"] is True

    res = await client.get("/v1/compliance/sources", headers=API_KEY_HEADERS)
    assert res.status_code == 200
    urls = [s["url"] for s in res.json()]
    assert payload["url"] in urls


async def test_create_source_unknown_jurisdiction(client):
    res = await client.post(
        "/v1/compliance/sources",
        json={
            "jurisdiction_code": "ZZ-NOPE",
            "name": "x",
            "url": "https://example.test/x",
        },
        headers=API_KEY_HEADERS,
    )
    assert res.status_code == 404


async def test_versions_unknown_citation_returns_empty(client):
    res = await client.get(
        "/v1/compliance/regulations/No%20Such%20Citation/versions",
        headers=API_KEY_HEADERS,
    )
    assert res.status_code == 200
    assert res.json() == []


async def test_review_queue_requires_role(client):
    res = await client.get("/v1/compliance/obligations/review-queue")
    assert res.status_code == 401

    res = await client.get(
        "/v1/compliance/obligations/review-queue",
        headers={"X-API-Key": "wrong-key"},
    )
    assert res.status_code == 401


async def test_tenant_user_cannot_read_other_org(client, session):
    """A key bound to org A must not read org B, and must still read org A."""
    org_a = Organization(id=uuid.uuid4(), legal_name=f"Tenant A {uuid.uuid4().hex[:6]}")
    org_b = Organization(id=uuid.uuid4(), legal_name=f"Tenant B {uuid.uuid4().hex[:6]}")
    session.add_all([org_a, org_b])
    await session.flush()

    api_key = f"tenant-key-{uuid.uuid4().hex}"
    user = User(
        id=uuid.uuid4(),
        org_id=org_a.id,
        email=f"user-{uuid.uuid4().hex}@example.test",
        role="admin",
        api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
        is_active=True,
    )
    session.add(user)
    await session.commit()

    try:
        headers = {"X-API-Key": api_key}

        own = await client.get(f"/v1/compliance/organizations/{org_a.id}", headers=headers)
        assert own.status_code == 200, own.text
        assert own.json()["id"] == str(org_a.id)

        other = await client.get(f"/v1/compliance/organizations/{org_b.id}", headers=headers)
        assert other.status_code == 403, other.text

        # Cross-org bootstrap key still works (ops/admin path).
        admin = await client.get(
            f"/v1/compliance/organizations/{org_b.id}", headers=API_KEY_HEADERS
        )
        assert admin.status_code == 200, admin.text
    finally:
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Organization).where(Organization.id.in_([org_a.id, org_b.id])))
        await session.commit()


async def test_bootstrap_key_may_create_organization(client):
    name = f"API Created {uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/v1/compliance/organizations",
        json={"legal_name": name, "industry": "fintech"},
        headers=API_KEY_HEADERS,
    )
    assert res.status_code == 201, res.text
    org_id = res.json()["id"]

    from agent_api.database import async_session

    async with async_session() as s:
        await s.execute(delete(Organization).where(Organization.id == uuid.UUID(org_id)))
        await s.commit()


async def test_tenant_user_cannot_create_organization(client, session):
    api_key = f"tenant-key-{uuid.uuid4().hex}"
    org = Organization(id=uuid.uuid4(), legal_name=f"Tenant {uuid.uuid4().hex[:6]}")
    session.add(org)
    await session.flush()
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        email=f"user-{uuid.uuid4().hex}@example.test",
        role="admin",
        api_key_hash=hashlib.sha256(api_key.encode()).hexdigest(),
        is_active=True,
    )
    session.add(user)
    await session.commit()

    try:
        res = await client.post(
            "/v1/compliance/organizations",
            json={"legal_name": "Should Not Exist"},
            headers={"X-API-Key": api_key},
        )
        assert res.status_code == 403, res.text
    finally:
        await session.execute(delete(User).where(User.id == user.id))
        await session.execute(delete(Organization).where(Organization.id == org.id))
        await session.commit()
