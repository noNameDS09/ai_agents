"""Compliance-specific settings.

Extends the generic agent_api config with compliance domain settings.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings

# Remove empty env vars (same pattern as agent_api/config.py)
for _key in ("COMPLIANCE_EMBEDDING_MODEL", "COMPLIANCE_EMBEDDING_DIM",
             "COMPLIANCE_QDRANT_URL", "COMPLIANCE_EVIDENCE_PATH"):
    if os.environ.get(_key, "").strip() == "":
        os.environ.pop(_key, None)


class ComplianceSettings(BaseSettings):
    # Embeddings
    embedding_provider: str = Field(
        "openrouter",
        description="Embedding provider: 'openrouter' (free API) or 'local' (sentence-transformers)",
    )
    embedding_model: str = Field(
        "nvidia/llama-nemotron-embed-vl-1b-v2:free",
        description="Embedding model name (OpenRouter model ID or HuggingFace model name)",
    )
    embedding_dim: int = Field(2048, description="Embedding dimension (must match model)")

    # Vector store
    qdrant_url: str = Field("http://localhost:6333", description="Qdrant server URL")
    qdrant_collection: str = Field("compliance_chunks", description="Qdrant collection name")

    # Evidence storage
    evidence_storage_path: str = Field("./data/evidence", description="Local evidence file storage path")

    # Scheduled jobs
    apscheduler_enabled: bool = Field(True, description="Enable APScheduler background jobs")
    regulatory_fetch_interval_hours: int = Field(6, description="Regulatory source fetch interval")
    deadline_check_interval_hours: int = Field(1, description="Deadline/escalation check interval")

    # RBAC
    default_role: str = Field("viewer", description="Default role for new users")

    # Compliance-specific
    default_jurisdiction: str = Field("US-FEDERAL", description="Default jurisdiction code")
    max_evidence_size_bytes: int = Field(50 * 1024 * 1024, description="Max evidence file size (50MB)")

    model_config = {
        "env_file": ".dev.env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
        "env_prefix": "COMPLIANCE_",
    }


compliance_settings = ComplianceSettings()