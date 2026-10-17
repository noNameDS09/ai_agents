"""Service-layer tests against the real test database.

Each test runs entirely inside one `asyncio.run` with its own engine and
session, so SQLAlchemy/asyncpg never crosses asyncio loops and tests are
fully isolated from one another.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_api.database import Base
from agent_api.service.agent import AgentService

# Resolve the test database URL without importing the pydantic settings
# singleton at module import time (settings is env-driven).
from agent_api.config import settings  # noqa: E402

TEST_URL = settings.test_database_url or settings.database_url


def _run(coro):
    return asyncio.run(coro)


async def _fresh_session():
    """Create a fresh engine + session for one isolated test."""
    engine = create_async_engine(TEST_URL, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session = session_factory()
    return engine, session


def _fake_graph_result(response: str, tool_calls=None, steps: int = 2):
    return {
        "response": response,
        "tool_calls": tool_calls or [],
        "steps": steps,
    }


def test_service_chat_persists_turns():
    async def _inner():
        engine, session = await _fresh_session()
        try:
            service = AgentService(session)
            with patch(
                "agent_api.service.agent.run_graph",
                return_value=_fake_graph_result(
                    "396",
                    [{"name": "calculator", "arguments": {"expression": "23*17"}}],
                ),
            ):
                result = await service.chat("what is 23*17?", None)

            assert result["response"] == "396"
            thread_id = result["thread_id"]
            uuid.UUID(thread_id)

            history = await service.get_history(thread_id)
            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "what is 23*17?"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "396"
            assert history[1]["tool_calls"][0]["name"] == "calculator"
        finally:
            await session.close()
            await engine.dispose()

    _run(_inner())


def test_service_chat_reuses_thread():
    async def _inner():
        engine, session = await _fresh_session()
        try:
            service = AgentService(session)
            with patch(
                "agent_api.service.agent.run_graph",
                return_value=_fake_graph_result("again"),
            ):
                r1 = await service.chat("first", None)
                thread_id = r1["thread_id"]
                r2 = await service.chat("second", thread_id)

            assert r1["thread_id"] == thread_id
            assert r2["thread_id"] == thread_id
            history = await service.get_history(thread_id)
            assert len(history) == 4  # 2 turns x 2 messages
        finally:
            await session.close()
            await engine.dispose()

    _run(_inner())


def test_service_get_history_unknown_thread():
    async def _inner():
        engine, session = await _fresh_session()
        try:
            service = AgentService(session)
            history = await service.get_history(str(uuid.uuid4()))
            assert history == []
        finally:
            await session.close()
            await engine.dispose()

    _run(_inner())


def test_service_chat_thread_must_exist():
    async def _inner():
        engine, session = await _fresh_session()
        try:
            service = AgentService(session)
            with patch(
                "agent_api.service.agent.run_graph",
                return_value=_fake_graph_result("x"),
            ):
                try:
                    await service.chat("hi", str(uuid.uuid4()))
                    raise AssertionError("expected ValueError")
                except ValueError as exc:
                    assert "not found" in str(exc)
        finally:
            await session.close()
            await engine.dispose()

    _run(_inner())


def test_service_health():
    async def _inner():
        engine, session = await _fresh_session()
        try:
            service = AgentService(session)
            result = await service.health()
            assert result["database"] == "ok"
            assert result["inference_configured"] is True
        finally:
            await session.close()
            await engine.dispose()

    _run(_inner())
