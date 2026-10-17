"""LangGraph state graph: LLM ↔ ToolNode loop with Postgres checkpointer.

The checkpointer (`PostgresSaver`) is synchronous, so graph execution is run
inside `asyncio.to_thread` from the service layer to avoid blocking the
FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool as lc_tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.checkpoint.postgres import PostgresSaver

from .config import settings
from .tools import (
    TOOL_NAMES,
    calculator as calc_impl,
    current_time as time_impl,
    knowledge_base_lookup as kb_impl,
)

logger = logging.getLogger("agent-api.graph")

SYSTEM_PROMPT = (
    "You are a helpful general-purpose assistant with access to tools. "
    "Use the available tools when they can answer the user's request, then "
    "give the final answer in plain language. Do not ask the user for "
    "confirmation before calling a tool. Only call tools whose names appear "
    "in the tool list."
)


# LangChain @tool wrappers around the allowlisted tools. Function names must
# match the tool allowlist exactly because langchain-core derives the tool
# name from the function name.
@lc_tool
def calculator(expression: str) -> str:
    """Evaluate a small arithmetic expression using + - * / % // ** and ()"""
    return calc_impl(__import_agent_args("calculator", expression=expression))


@lc_tool
def current_time(format: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    """Return the current UTC time formatted with a strftime format string"""
    return time_impl(__import_agent_args("current_time", format=format))


@lc_tool
def knowledge_base_lookup(query: str) -> str:
    """Look up a fact in the static knowledge base stub"""
    return kb_impl(__import_agent_args("knowledge_base_lookup", query=query))


def __import_agent_args(tool_name: str, **kwargs):
    """Validate tool-call arguments against the Pydantic args schema."""
    from .tools import TOOL_REGISTRY

    args_schema, _func = TOOL_REGISTRY[tool_name]
    return args_schema(**kwargs)


_LC_TOOLS = [calculator, current_time, knowledge_base_lookup]
_LC_TOOL_NAMES = frozenset(t.name for t in _LC_TOOLS)

# Safety: the LangChain tool names must match the allowlisted tool names.
assert _LC_TOOL_NAMES == TOOL_NAMES, (
    f"LangChain tool names {_LC_TOOL_NAMES} != allowlist {TOOL_NAMES}"
)


def _build_graph(checkpointer: PostgresSaver | None = None) -> Any:
    model = ChatOpenAI(
        model=settings.openrouter_model,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
        temperature=0,
        default_headers={
            "HTTP-Referer": settings.openrouter_http_referer,
            "X-Title": settings.openrouter_x_title,
        },
    ).bind_tools(_LC_TOOLS)

    def call_model(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = model.invoke(messages, config)
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("model", call_model)
    builder.add_node("tools", ToolNode(_LC_TOOLS))
    builder.set_entry_point("model")
    builder.add_conditional_edges("model", tools_condition)
    builder.add_edge("tools", "model")
    return builder.compile(checkpointer=checkpointer)


def build_graph() -> Any:
    """Compile the LangGraph app (no checkpointer). Stateless runs."""
    return _build_graph(checkpointer=None)


def build_graph_with_checkpointer() -> tuple[Any, object]:
    """Compile the LangGraph app with a Postgres checkpointer (stateful).

    PostgresSaver is synchronous, so the psycopg connection is created here
    (on the worker thread), not on the FastAPI event loop. Returns the
    compiled app plus the underlying connection, which the caller must close.
    """
    import psycopg

    conn = psycopg.connect(settings.psycopg_database_url, autocommit=True)
    saver = PostgresSaver(conn)
    saver.setup()
    return _build_graph(checkpointer=saver), conn


async def run_graph(
    messages: list[dict[str, str]],
    thread_id: str | None,
    model_override: str | None = None,
) -> dict[str, Any]:
    """Run the agent graph in a worker thread.

    `messages` uses role/content dicts (roles restricted to 'user' by the API
    layer). Returns a dict with assistant text, tool calls, and step count.
    """
    langchain_messages = [
        HumanMessage(content=m["content"])
        if m["role"] == "user"
        else AIMessage(content=m["content"])
        for m in messages
    ]

    def _run() -> dict[str, Any]:
        config: RunnableConfig = {}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}
        if thread_id:
            app, conn = build_graph_with_checkpointer()
            try:
                return app.invoke({"messages": langchain_messages}, config)
            finally:
                conn.close()
        return build_graph().invoke({"messages": langchain_messages}, config)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        logger.exception("graph execution failed")
        raise RuntimeError(f"agent execution failed: {exc}") from exc

    final_messages = result.get("messages", [])
    assistant_text = ""
    tool_calls: list[dict[str, Any]] = []
    steps = 0
    for msg in final_messages:
        steps += 1
        if isinstance(msg, AIMessage):
            if msg.content:
                assistant_text = msg.content
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(
                        {
                            "name": tc.get("name"),
                            "arguments": tc.get("args", {}),
                        }
                    )
        elif isinstance(msg, ToolMessage):
            steps += 1

    # Append a short tool-citation line so callers can see which tools ran.
    if tool_calls:
        names = ", ".join(tc["name"] for tc in tool_calls)
        citation = f"\n\n_(tool called: {names})_"
        assistant_text = (assistant_text or "") + citation

    return {
        "response": assistant_text or "(no response)",
        "tool_calls": tool_calls,
        "steps": max(steps, 1),
    }
