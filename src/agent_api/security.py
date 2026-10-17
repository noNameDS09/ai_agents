"""Security controls: API key auth, rate limiting, input validation."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from .config import settings

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# Roles the client is allowed to send. System prompts are server-side only.
ALLOWED_ROLES: frozenset[str] = frozenset({"user"})


@dataclass
class TokenBucket:
    """Simple in-memory token bucket per API key (not shared across processes)."""

    max_requests: int
    window_seconds: int
    _timestamps: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def check(self, key: str) -> float | None:
        """Return retry-after seconds if limited, None if allowed."""
        now = time.monotonic()
        window_start = now - self.window_seconds
        stamps = [t for t in self._timestamps[key] if t > window_start]
        self._timestamps[key] = stamps
        if len(stamps) >= self.max_requests:
            retry_after = self.window_seconds - (now - stamps[0])
            return max(retry_after, 0.0)
        stamps.append(now)
        return None


rate_limiter = TokenBucket(
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)


def validate_api_key(api_key: str | None) -> str:
    """Constant-time comparison against the configured API key."""
    if not api_key or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API key",
        )
    return api_key


def validate_message(message: str) -> str:
    """Sanitize and length-check a user message."""
    if not message or not message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message must not be empty",
        )
    if len(message) > settings.max_message_length:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"message exceeds {settings.max_message_length} characters",
        )
    # Reject raw control characters except common whitespace.
    for ch in message:
        if ord(ch) < 32 and ch not in "\t\n\r":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="message contains invalid control characters",
            )
    return message.strip()


async def require_auth(request: Request) -> str:
    """FastAPI dependency: authenticate + rate-limit a request.

    Raised HTTPException objects are converted to proper error responses by
    FastAPI (unlike exceptions raised inside middleware).
    """
    api_key = request.headers.get("X-API-Key")
    validate_api_key(api_key)
    await enforce_rate_limit(request, api_key)
    return api_key


AuthDependency = Annotated[str, Depends(require_auth)]


async def enforce_rate_limit(request: Request, api_key: str) -> None:
    retry_after = rate_limiter.check(api_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate limit exceeded",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
