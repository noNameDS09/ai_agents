"""Pytest fixtures: test env + ASGI client.

Environment variables are set at module top so the pydantic-settings
singleton (`agent_api.config.settings`) reads test values at import time.
"""

from __future__ import annotations

import os

os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test1234567890abcdef")
os.environ.setdefault("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/agent_test?host=%2Frun%2Fpostgresql",
)
os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres@/agent_test?host=%2Frun%2Fpostgresql",
)
os.environ.setdefault("TRUSTED_HOSTS", '["testserver","localhost","127.0.0.1"]')
os.environ.setdefault("RATE_LIMIT_REQUESTS", "10000")
os.environ.setdefault("RATE_LIMIT_WINDOW_SECONDS", "60")
os.environ.setdefault("MAX_MESSAGE_LENGTH", "4000")
os.environ.setdefault("MAX_REQUEST_BODY_BYTES", "262144")

from typing import AsyncIterator  # noqa: E402

import pytest
from httpx import ASGITransport, AsyncClient  # noqa: E402

from agent_api.main import create_app  # noqa: E402
from agent_api.security import rate_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter._timestamps.clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
