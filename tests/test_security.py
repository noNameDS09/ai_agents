"""Unit tests for security controls (no DB, no network)."""

from __future__ import annotations

from fastapi import HTTPException

from agent_api.config import settings
from agent_api.security import validate_api_key, validate_message, rate_limiter


def test_validate_api_key_valid():
    assert validate_api_key(settings.api_key) == settings.api_key


def test_validate_api_key_missing():
    try:
        validate_api_key(None)  # type: ignore[arg-type]
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_validate_api_key_wrong():
    try:
        validate_api_key("wrong-key")
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 401


def test_validate_message_ok():
    assert validate_message("hello world") == "hello world"


def test_validate_message_whitespace_stripped():
    assert validate_message("  hi  ") == "hi"


def test_validate_message_empty():
    for bad in ["", "   ", "\t\n"]:
        try:
            validate_message(bad)
            raise AssertionError(f"expected HTTPException for {bad!r}")
        except HTTPException as exc:
            assert exc.status_code == 400


def test_validate_message_too_long():
    too_long = "x" * (settings.max_message_length + 1)
    try:
        validate_message(too_long)
        raise AssertionError("expected HTTPException")
    except HTTPException as exc:
        assert exc.status_code == 400


def test_rate_limit_allows_then_blocks():
    rate_limiter._timestamps.clear()
    key = "user-1"
    for _ in range(rate_limiter.max_requests):
        assert rate_limiter.check(key) is None
    retry = rate_limiter.check(key)
    assert retry is not None
    assert retry >= 0.0


def test_rate_limit_different_keys_isolated():
    rate_limiter._timestamps.clear()
    assert rate_limiter.check("a") is None
    assert rate_limiter.check("b") is None
