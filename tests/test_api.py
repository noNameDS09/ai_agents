"""HTTP endpoint tests.

The service layer is stubbed so these tests exercise auth, rate limiting,
validation, request/response shape, and routing — without touching PostgreSQL
or OpenRouter. Service-layer DB behavior is covered in test_service.py.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from agent_api.main import create_app
from agent_api.security import rate_limiter
from agent_api.service.agent import AgentService, get_service


class FakeService(AgentService):
    def __init__(self, chat_return=None, history_return=None):
        self.chat_return = chat_return or {
            "thread_id": "11111111-1111-1111-1111-111111111111",
            "response": "ok",
            "tool_calls": [],
            "steps": 1,
        }
        self.history_return = history_return or []

    async def chat(self, message: str, thread_id: str | None, model_override: str | None = None) -> dict[str, Any]:
        return dict(self.chat_return)

    async def get_history(self, thread_id: str) -> list[dict[str, Any]]:
        return list(self.history_return)

    async def health(self) -> dict[str, Any]:
        return {"database": "ok", "inference_configured": True}


def _client_with(fake: FakeService | None = None):
    app = create_app()

    async def _override_get_service():
        yield fake or FakeService()

    app.dependency_overrides[get_service] = _override_get_service
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
async def client():
    async with _client_with() as ac:
        yield ac


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter._timestamps.clear()


def _headers() -> dict[str, str]:
    return {"X-API-Key": "test-api-key"}


@pytest.mark.asyncio
async def test_chat_success(client):
    fake = FakeService(chat_return={
        "thread_id": "11111111-1111-1111-1111-111111111111",
        "response": "396",
        "tool_calls": [{"name": "calculator", "arguments": {"expression": "23 * 17 + 5"}}],
        "steps": 2,
    })
    async with _client_with(fake) as ac:
        resp = await ac.post("/v1/chat", json={"message": "what is 23 * 17 + 5?"}, headers=_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["response"] == "396"
    assert data["tool_calls"][0]["name"] == "calculator"
    assert data["steps"] == 2


@pytest.mark.asyncio
async def test_chat_requires_api_key(client):
    resp = await client.post("/v1/chat", json={"message": "hello"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_invalid_api_key(client):
    resp = await client.post(
        "/v1/chat", json={"message": "hello"}, headers={"X-API-Key": "wrong"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    resp = await client.post(
        "/v1/chat", json={"message": ""}, headers=_headers()
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_paid_model_override_rejected(client):
    resp = await client.post(
        "/v1/chat",
        json={"message": "hi", "model": "anthropic/claude-3-opus"},
        headers=_headers(),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_invalid_thread_id(client):
    resp = await client.post(
        "/v1/chat",
        json={"message": "hi", "thread_id": "not-a-uuid"},
        headers=_headers(),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_rate_limit(client):
    rate_limiter.max_requests = 1
    try:
        async with _client_with() as ac:
            await ac.post("/v1/chat", json={"message": "hi"}, headers=_headers())
            r2 = await ac.post("/v1/chat", json={"message": "hi"}, headers=_headers())
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers
    finally:
        rate_limiter.max_requests = 10000


@pytest.mark.asyncio
async def test_get_thread_not_found(client):
    async with _client_with(FakeService(history_return=[])) as ac:
        resp = await ac.get(
            "/v1/threads/33333333-3333-3333-3333-333333333333", headers=_headers()
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_thread_ok(client):
    history = [{"role": "user", "content": "hi", "created_at": "2026-01-01T00:00:00+00:00"}]
    async with _client_with(FakeService(history_return=history)) as ac:
        resp = await ac.get(
            "/v1/threads/44444444-4444-4444-4444-444444444444", headers=_headers()
        )
    assert resp.status_code == 200
    assert resp.json()["thread_id"] == "44444444-4444-4444-4444-444444444444"
    assert resp.json()["messages"] == history


@pytest.mark.asyncio
async def test_list_tools(client):
    resp = await client.get("/v1/tools", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    names = {t["name"] for t in data["tools"]}
    assert names == {"calculator", "current_time", "knowledge_base_lookup"}


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["database"] == "ok"
    assert data["inference_configured"] is True
