"""Unit tests for the LangGraph agent loop (OpenRouter stubbed, no network)."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from langchain_core.messages import AIMessage

from agent_api.graph import run_graph, build_graph


class _FakeModel:
    """Stub in place of ChatOpenAI. Returns canned responses in order."""

    def __init__(self, *args: Any, **kwargs: Any):
        self.responses: list[AIMessage] = []

    def bind_tools(self, tools: Any):
        return self

    def invoke(self, messages: Any, config: Any = None) -> AIMessage:
        if not self.responses:
            raise AssertionError("no canned response configured")
        return self.responses.pop(0)


def _canned_text(text: str) -> AIMessage:
    return AIMessage(content=text)


def _canned_tool_call(name: str, arguments: dict[str, Any]) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"id": "call_1", "name": name, "args": arguments}],
    )


import pytest  # noqa: E402


@pytest.mark.asyncio
async def test_graph_single_turn_answer():
    """Model answers directly without tools."""
    fake = _FakeModel()
    fake.responses = [_canned_text("The answer is 42")]
    with patch("agent_api.graph.ChatOpenAI", return_value=fake):
        result = await run_graph(
            [{"role": "user", "content": "what is the meaning of life"}],
            None,
        )
    assert result["response"] == "The answer is 42"
    assert result["tool_calls"] == []
    assert result["steps"] >= 1


@pytest.mark.asyncio
async def test_graph_uses_tool_then_answers():
    """Model calls calculator, then answers with the result."""
    fake = _FakeModel()
    fake.responses = [
        _canned_tool_call("calculator", {"expression": "23 * 17 + 5"}),
        _canned_text("23 * 17 + 5 = 396"),
    ]
    with patch("agent_api.graph.ChatOpenAI", return_value=fake):
        result = await run_graph([{"role": "user", "content": "what is 23 * 17 + 5?"}], None)
    assert result["response"] == "23 * 17 + 5 = 396\n\n_(tool called: calculator)_"
    assert result["tool_calls"] == [
        {"name": "calculator", "arguments": {"expression": "23 * 17 + 5"}}
    ]
    assert result["steps"] >= 2


@pytest.mark.asyncio
async def test_graph_with_thread_id_uses_checkpointer():
    """Stateful run with a thread_id uses the Postgres checkpointer."""
    fake = _FakeModel()
    fake.responses = [_canned_text("hi")]
    with patch("agent_api.graph.ChatOpenAI", return_value=fake):
        result = await run_graph(
            [{"role": "user", "content": "say hi"}],
            "00000000-0000-0000-0000-000000000001",
        )
    assert result["response"] == "hi"


def test_build_graph_compiles():
    app = build_graph()
    assert app is not None
