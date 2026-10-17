"""Tavily MCP client helper.

Wraps the remote Tavily MCP server (https://mcp.tavily.com/mcp/) so that
agent tools can perform web search and content extraction via the MCP
protocol.  All functions are async; synchronous wrappers are provided for
use inside LangChain @tool functions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from .config import settings

logger = logging.getLogger("agent-api.tavily-mcp")

# Default search parameters
_DEFAULT_SEARCH_DEPTH = "basic"
_DEFAULT_MAX_RESULTS = 5


def _mcp_url() -> str:
    """Build the Tavily MCP server URL with the API key."""
    base = settings.tavily_mcp_url.rstrip("/")
    if settings.tavily_api_key:
        return f"{base}/?tavilyApiKey={settings.tavily_api_key}"
    return base


async def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    """Connect to the Tavily MCP server, call a tool, and return the text result."""
    if not settings.tavily_api_key:
        return "tavily error: TAVILY_API_KEY is not configured"

    url = _mcp_url()
    try:
        async with streamable_http_client(url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                # Extract text content from the result
                texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        texts.append(content.text)
                    else:
                        texts.append(str(content))
                return "\n".join(texts) if texts else str(result)
    except Exception as exc:
        logger.exception("Tavily MCP call failed: %s", tool_name)
        return f"tavily error: {exc}"


async def tavily_search_async(
    query: str,
    search_depth: str = _DEFAULT_SEARCH_DEPTH,
    max_results: int = _DEFAULT_MAX_RESULTS,
    topic: str = "general",
    include_answer: bool = True,
    include_raw_content: bool = False,
) -> str:
    """Search the web via Tavily MCP and return formatted results."""
    args: dict[str, Any] = {
        "query": query,
        "search_depth": search_depth,
        "max_results": max_results,
        "topic": topic,
        "include_answer": include_answer,
        "include_raw_content": include_raw_content,
    }
    return await _call_mcp_tool("tavily_search", args)


async def tavily_extract_async(
    urls: list[str],
    extract_depth: str = "basic",
    include_images: bool = False,
) -> str:
    """Extract clean content from URLs via Tavily MCP."""
    args: dict[str, Any] = {
        "urls": urls,
        "extract_depth": extract_depth,
        "include_images": include_images,
    }
    return await _call_mcp_tool("tavily_extract", args)


async def tavily_crawl_async(
    url: str,
    max_depth: int = 1,
    max_breadth: int = 20,
    limit: int = 50,
) -> str:
    """Crawl a website starting from a URL via Tavily MCP."""
    args: dict[str, Any] = {
        "url": url,
        "max_depth": max_depth,
        "max_breadth": max_breadth,
        "limit": limit,
    }
    return await _call_mcp_tool("tavily_crawl", args)


async def tavily_map_async(url: str, max_depth: int = 1) -> str:
    """Map a website's structure (discover URLs) via Tavily MCP."""
    args: dict[str, Any] = {"url": url, "max_depth": max_depth}
    return await _call_mcp_tool("tavily_map", args)


async def tavily_research_async(query: str, model: str = "auto") -> str:
    """Perform comprehensive multi-source research via Tavily MCP."""
    args: dict[str, Any] = {"input": query, "model": model}
    return await _call_mcp_tool("tavily_research", args)


# Synchronous wrappers for use inside LangChain @tool functions
def tavily_search_sync(**kwargs) -> str:
    return asyncio.run(tavily_search_async(**kwargs))


def tavily_extract_sync(**kwargs) -> str:
    return asyncio.run(tavily_extract_async(**kwargs))


def tavily_crawl_sync(**kwargs) -> str:
    return asyncio.run(tavily_crawl_async(**kwargs))


def tavily_map_sync(**kwargs) -> str:
    return asyncio.run(tavily_map_async(**kwargs))


def tavily_research_sync(**kwargs) -> str:
    return asyncio.run(tavily_research_async(**kwargs))