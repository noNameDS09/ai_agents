"""Regulatory source fetching — retrieves content from authoritative sources.

Uses Tavily MCP (url_extract) for HTML-heavy regulator pages, with a direct
httpx fallback for plain-text/feeds. Fetching is idempotent by content hash.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import httpx

from .diffing import content_sha256, detect_change, DiffResult

logger = logging.getLogger("compliance.services.source_fetching")


@dataclass
class FetchedSource:
    url: str
    raw_text: str
    content_sha256: str
    http_status: int
    fetched_at: datetime
    change: DiffResult
    method: str  # "tavily" | "direct"


async def fetch_url_direct(url: str, timeout: float = 30.0) -> tuple[str, int]:
    """Fetch a URL directly with httpx (plain text / feeds)."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "ComplianceOS/1.0"})
        return resp.text, resp.status_code


async def fetch_url_tavily(url: str, api_key: str, timeout: float = 60.0) -> tuple[str, int]:
    """Extract clean text from a URL via Tavily's extract endpoint (REST fallback)."""
    if not api_key:
        raise ValueError("TAVILY_API_KEY not configured")
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(
            "https://api.tavily.com/extract",
            json={"api_key": api_key, "urls": [url], "extract_depth": "advanced"},
        )
        data = resp.json()
        results = data.get("results", [])
        if not results:
            raise ValueError(f"Tavily returned no results for {url}: {data.get('failed_results', [])}")
        return results[0].get("raw_content", ""), resp.status_code


async def fetch_source(
    url: str,
    previous_sha256: Optional[str] = None,
    prefer_tavily: bool = True,
    tavily_api_key: Optional[str] = None,
) -> FetchedSource:
    """Fetch a source and detect changes vs the previous version."""
    method = "direct"
    raw_text = ""
    http_status = 0

    if prefer_tavily and tavily_api_key:
        try:
            raw_text, http_status = await fetch_url_tavily(url, tavily_api_key)
            method = "tavily"
        except Exception as exc:
            logger.warning("Tavily extract failed for %s: %s — falling back to direct", url, exc)

    if not raw_text:
        raw_text, http_status = await fetch_url_direct(url)

    sha = content_sha256(raw_text)
    change = detect_change(raw_text, previous_sha256)

    return FetchedSource(
        url=url,
        raw_text=raw_text,
        content_sha256=sha,
        http_status=http_status,
        fetched_at=datetime.now(timezone.utc),
        change=change,
        method=method,
    )