"""Embedding provider — OpenRouter (primary) with local sentence-transformers fallback.

OpenRouter exposes 33 embedding models via /api/v1/embeddings, 3 of which are free:
  - nvidia/llama-nemotron-embed-vl-1b-v2:free  (2048-dim, 99.97% uptime)  ← default
  - nvidia/nemotron-3-embed-1b:free             (2048-dim, 69.17% uptime)
  - liquid/lfm-2.5-embedding-350m:free          (1024-dim, unconfirmed)

For sensitive data (evidence documents), use local sentence-transformers
(all-MiniLM-L6-v2, 384-dim) to keep data on-server.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from ..config import compliance_settings

logger = logging.getLogger("compliance.rag.embeddings")

# Default model and dimension
_DEFAULT_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
_DEFAULT_DIM = 2048


def _provider() -> str:
    """Return the configured embedding provider: 'openrouter' or 'local'."""
    return getattr(compliance_settings, "embedding_provider", "openrouter")


def _openrouter_embed(texts: List[str], model: str) -> List[List[float]]:
    """Embed texts via OpenRouter's /api/v1/embeddings endpoint."""
    import httpx

    from agent_api.config import settings

    url = f"{settings.openrouter_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}
    response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
    response.raise_for_status()
    data = response.json()
    # Sort by index to preserve order
    embeddings = sorted(data["data"], key=lambda x: x["index"])
    return [e["embedding"] for e in embeddings]


# Lazy-loaded local model
_local_model = None
_local_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"


def _local_embed(texts: List[str], model_name: str) -> List[List[float]]:
    """Embed texts using local sentence-transformers."""
    global _local_model, _local_model_name
    if model_name != _local_model_name or _local_model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading local embedding model: %s", model_name)
        _local_model = SentenceTransformer(model_name)
        _local_model_name = model_name
    embeddings = _local_model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


def embed_texts(texts: List[str], model: Optional[str] = None, provider: Optional[str] = None) -> List[List[float]]:
    """Embed a list of texts and return list of float vectors.

    Args:
        texts: Input texts to embed.
        model: Override model name. Defaults to config value.
        provider: Override provider ('openrouter' or 'local'). Defaults to config.

    Returns:
        List of embedding vectors.
    """
    if not texts:
        return []

    prov = provider or _provider()
    mdl = model or compliance_settings.embedding_model

    if prov == "openrouter":
        try:
            return _openrouter_embed(texts, mdl)
        except Exception as exc:
            logger.warning("OpenRouter embedding failed (%s), falling back to local", exc)
            prov = "local"
            mdl = "sentence-transformers/all-MiniLM-L6-v2"

    return _local_embed(texts, mdl)


def embed_single(text: str, model: Optional[str] = None, provider: Optional[str] = None) -> List[float]:
    """Embed a single text and return a float vector."""
    result = embed_texts([text], model, provider)
    return result[0] if result else []


def embedding_dim(model: Optional[str] = None, provider: Optional[str] = None) -> int:
    """Return the embedding dimension for the configured model."""
    prov = provider or _provider()
    mdl = model or compliance_settings.embedding_model
    if prov == "openrouter":
        # Known dimensions for free models
        dims = {
            "nvidia/llama-nemotron-embed-vl-1b-v2:free": 2048,
            "nvidia/nemotron-3-embed-1b:free": 2048,
            "liquid/lfm-2.5-embedding-350m:free": 1024,
        }
        return dims.get(mdl, 2048)
    # Local
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(mdl)
    return m.get_sentence_embedding_dimension()