"""Unit tests for allowlisted tools (no DB, no network)."""

from __future__ import annotations

from agent_api.tools import (
    CalculatorArgs,
    CurrentTimeArgs,
    KnowledgeBaseLookupArgs,
    calculator,
    current_time,
    knowledge_base_lookup,
    TOOL_NAMES,
)


def test_tool_allowlist_names():
    assert TOOL_NAMES == {"calculator", "current_time", "knowledge_base_lookup"}


def test_calculator_basic():
    assert calculator(CalculatorArgs(expression="23 * 17 + 5")) == "396"
    assert calculator(CalculatorArgs(expression="2 + 2")) == "4"
    assert calculator(CalculatorArgs(expression="10 / 4")) == "2.5"
    assert calculator(CalculatorArgs(expression="(3 + 4) * 2")) == "14"


def test_calculator_rejects_unsafe():
    for bad in ["__import__('os')", "2; drop table", "2 < 3", "true and false"]:
        result = calculator(CalculatorArgs(expression=bad))
        assert result.startswith("calculator error"), bad


def test_calculator_division_by_zero():
    result = calculator(CalculatorArgs(expression="1 / 0"))
    assert result.startswith("calculator error")


def test_current_time():
    out = current_time(CurrentTimeArgs(format="%Y-%m-%d %H:%M:%S UTC"))
    assert out.endswith(" UTC")
    assert len(out) == len("2026-01-01 00:00:00 UTC")


def test_knowledge_base_lookup_found():
    assert knowledge_base_lookup(KnowledgeBaseLookupArgs(query="capital of france")) == "Paris"
    assert knowledge_base_lookup(KnowledgeBaseLookupArgs(query="largest planet")) == "Jupiter"


def test_knowledge_base_lookup_not_found():
    result = knowledge_base_lookup(KnowledgeBaseLookupArgs(query="nothing here"))
    assert result.startswith("No KB entry found")
