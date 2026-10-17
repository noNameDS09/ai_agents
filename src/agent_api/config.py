"""Application configuration.

Single source of truth: Pydantic Settings loaded from environment variables
(and `.dev.env` locally). Required settings fail fast at startup if missing.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("agent-api.config")

# Pydantic-settings treats empty env vars as present but invalid JSON for
# complex types (list[str]). Remove empty values so pydantic falls back to
# the .env file or the field default.
for _key in ("CORS_ORIGINS", "TRUSTED_HOSTS"):
    if os.environ.get(_key, "").strip() == "":
        os.environ.pop(_key, None)


class Settings(BaseSettings):
    app_name: str = "agent-api"
    app_version: str = "0.1.0"

    # Authentication / inference (required unless noted)
    api_key: str = Field(..., min_length=1, description="Client API key (X-API-Key header)")
    openrouter_api_key: str = Field(
        "", description="OpenRouter API key. Chat returns 503 when unset."
    )
    openrouter_model: str = Field(
        "nvidia/nemotron-3.5-lightning:free",
        description="Must be an OpenRouter free model (typically suffixed :free).",
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_x_title: str = "agent-api"

    # Tavily (MCP-based web search / extraction)
    tavily_api_key: str = Field(
        "", description="Tavily API key. Web search tools return an error when unset."
    )
    tavily_mcp_url: str = Field(
        "https://mcp.tavily.com/mcp/",
        description="Tavily MCP server URL (remote). API key appended as query param.",
    )

    # Database
    database_url: str
    test_database_url: str | None = None

    # Security / transport
    cors_origins: list[str] = ["*"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1"]
    rate_limit_requests: int = Field(60, ge=1)
    rate_limit_window_seconds: int = Field(60, ge=1)
    max_request_body_bytes: int = Field(262144, ge=1)
    max_message_length: int = Field(4000, ge=1)

    @field_validator("cors_origins", "trusted_hosts", mode="before")
    @classmethod
    def _parse_list_env(cls, v):
        """Parse list env vars: JSON array, comma-separated, or empty→default."""
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("openrouter_model")
    @classmethod
    def _warn_non_free_model(cls, v: str) -> str:
        if not v.endswith(":free"):
            logger.warning(
                "OPENROUTER_MODEL %r does not look like a free model. "
                "Verify it on https://openrouter.ai/models before deploying.",
                v,
            )
        return v

    model_config = {
        "env_file": ".dev.env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @computed_field  # type: ignore[misc]
    @property
    def psycopg_database_url(self) -> str:
        """psycopg-compatible DSN (strip the asyncpg driver prefix)."""
        if self.database_url.startswith("postgresql+asyncpg://"):
            return "postgresql://" + self.database_url[len("postgresql+asyncpg://") :]
        return self.database_url


settings = Settings()
