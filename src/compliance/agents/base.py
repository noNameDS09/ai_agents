"""Base agent contract and common sub-graph factory for ComplianceOS agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Type, TypeVar

from pydantic import BaseModel
from langgraph.graph import StateGraph, END

logger = logging.getLogger("compliance.agents.base")

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


@dataclass
class AgentContext:
    """Context passed to every agent run."""
    org_id: str
    thread_id: str
    checkpoint_ns: str
    db_session: Any  # AsyncSession
    qdrant_client: Any = None
    user_id: Optional[str] = None
    approval_callback: Optional[Callable] = None


class AgentContract(ABC):
    """Base contract for all compliance agents."""

    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    tool_allowlist: frozenset[str] = frozenset()
    requires_approval: bool = False
    max_retries: int = 2

    @abstractmethod
    async def run(self, input_data: BaseModel, ctx: AgentContext) -> BaseModel:
        """Execute the agent. Must write to audit chain."""
        ...

    @abstractmethod
    def validate_output(self, output: BaseModel) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        ...

    def build_subgraph(self, checkpointer=None):
        """Build a LangGraph sub-graph for this agent."""
        from langgraph.graph import StateGraph, END, MessagesState

        async def run_node(state):
            # Extract input from state
            input_data = self.input_schema(**state.get("input", {}))
            ctx = state.get("ctx")
            output = await self.run(input_data, ctx)
            errors = self.validate_output(output)
            return {"output": output.model_dump(), "errors": errors, "retries": state.get("retries", 0)}

        def validate_node(state):
            errors = state.get("errors", [])
            if errors:
                retries = state.get("retries", 0) + 1
                if retries <= self.max_retries:
                    return {"retries": retries, "should_retry": True}
                return {"retries": retries, "should_retry": False, "escalate": True}
            return {"should_retry": False, "escalate": False}

        def persist_node(state):
            # Persist output to DB + audit chain (implemented by subclass or orchestrator)
            return {"persisted": True}

        builder = StateGraph(dict)
        builder.add_node("run", run_node)
        builder.add_node("validate", validate_node)
        builder.add_node("persist", persist_node)
        builder.set_entry_point("run")
        builder.add_edge("run", "validate")
        builder.add_conditional_edges(
            "validate",
            lambda s: "run" if s.get("should_retry") else "persist",
        )
        builder.add_edge("persist", END)
        return builder.compile(checkpointer=checkpointer, name=self.name)