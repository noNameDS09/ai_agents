"""Allowlisted agent tools.

All tools are deterministic, local (no outbound network), and accept a
Pydantic-validated argument schema. Add a tool here *and* register it in
`graph.py`'s `TOOL_NAMES` allowlist before the model can invoke it.
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class CalculatorArgs(BaseModel):
    expression: str = Field(
        ...,
        description="A safe arithmetic expression using numbers and + - * / % // ** ( )",
        examples=["23 * 17 + 5"],
    )


class CurrentTimeArgs(BaseModel):
    format: str = Field(
        "%Y-%m-%d %H:%M:%S UTC",
        description="strftime format for the current UTC time",
    )


class KnowledgeBaseLookupArgs(BaseModel):
    query: str = Field(..., description="Free-text query to look up in the KB stub")


# Whitelisted AST node types for the calculator.
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError("only numeric literals are allowed")
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BoolOp) or isinstance(node, ast.Compare):
        raise ValueError("boolean/comparison operators are not allowed")
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def calculator(args: CalculatorArgs) -> str:
    """Evaluate a small arithmetic expression safely (no eval)."""
    try:
        tree = ast.parse(args.expression, mode="eval")
        result = _eval(tree)
    except Exception as exc:  # noqa: BLE001 - surface parse/eval errors to user
        return f"calculator error: {exc}"
    # Format nicely: drop trailing .0 for whole numbers.
    if result == int(result):
        return str(int(result))
    return str(result)


def current_time(args: CurrentTimeArgs) -> str:
    """Return the current UTC time formatted per `args.format`."""
    try:
        return datetime.now(timezone.utc).strftime(args.format)
    except Exception as exc:  # noqa: BLE001
        return f"current_time error: {exc}"


def knowledge_base_lookup(args: KnowledgeBaseLookupArgs) -> str:
    """Static knowledge-base stub (no retrieval pipeline)."""
    kb = {
        "capital of france": "Paris",
        "capital of japan": "Tokyo",
        "largest planet": "Jupiter",
        "speed of light": "299,792,458 meters per second",
    }
    key = args.query.strip().lower()
    return kb.get(key, f"No KB entry found for: {args.query}")


# Tool name -> (args_schema, callable). The model can only call names in this map.
TOOL_REGISTRY: dict[str, tuple[type[BaseModel], callable]] = {
    "calculator": (CalculatorArgs, calculator),
    "current_time": (CurrentTimeArgs, current_time),
    "knowledge_base_lookup": (KnowledgeBaseLookupArgs, knowledge_base_lookup),
}

TOOL_NAMES = frozenset(TOOL_REGISTRY)

__all__ = [
    "CalculatorArgs",
    "CurrentTimeArgs",
    "KnowledgeBaseLookupArgs",
    "calculator",
    "current_time",
    "knowledge_base_lookup",
    "TOOL_REGISTRY",
    "TOOL_NAMES",
]
