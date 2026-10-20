"""Embedding provider — OpenRouter (primary) with opt-in local fallback.

OpenRouter exposes embedding models via /api/v1/embeddings; the free ones:
  - nvidia/llama-nemotron-embed-vl-1b-v2:free  (2048-dim, 99.97% uptime)  ← default
  - nvidia/nemotron-3-embed-1b:free             (2048-dim, 69.17% uptime)
  - liquid/lfm-2.5-embedding-350m:free          (1024-dim, unconfirmed)

Design rules (important — this is a compliance index):
  1. Embeddings are requested in bounded batches with retry/backoff, because
     free-tier endpoints are rate limited and a single huge request is fragile.
  2. Failure is LOUD. We never silently swap the embedding model, because
     vectors from different models have different dimensions and different
     vector spaces. Mixing them in one Qdrant collection silently destroys
     retrieval quality (wrong citations), which is worse than an error.
  3. A local sentence-transformers fallback exists for sensitive evidence
     documents, but it is opt-in per call (`allow_fallback=True`) and callers
     must target a collection whose dimension matches.

For sensitive data (evidence documents), call with provider="local" to keep
data on-server (all-MiniLM-L6-v2, 384-dim) and use a separate collection.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from collections import OrderedDict
from typing import List, Optional, Tuple

from ..config import compliance_settings

logger = logging.getLogger("compliance.rag.embeddings")

# Default model and dimension
DEFAULT_EMBEDDING_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LOCAL_EMBEDDING_DIM = 384

# Known dimensions for the free OpenRouter embedding models.
KNOWN_DIMENSIONS = {
    "nvidia/llama-nemotron-embed-vl-1b-v2:free": 2048,
    "nvidia/nemotron-3-embed-1b:free": 2048,
    "liquid/lfm-2.5-embedding-350m:free": 1024,
    LOCAL_EMBEDDING_MODEL: LOCAL_EMBEDDING_DIM,
}

# Bounded batching: free-tier endpoints reject or time out on very large inputs.
DEFAULT_BATCH_SIZE = 32
MAX_RETRIES = 4
BASE_BACKOFF_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 90.0

# HTTP statuses worth retrying (rate limit / transient server / gateway).
RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504, 522, 524})

# In-process embedding cache. Free-tier embedding endpoints are slow and
# rate limited, and embeddings are deterministic, so caching by (model, sha256)
# makes re-indexing and repeated search queries effectively free.
# Note: process-local. A multi-worker deployment should move this to Redis.
_EMBED_CACHE: "OrderedDict[Tuple[str, str], List[float]]" = OrderedDict()
_EMBED_CACHE_MAX = 4096


class EmbeddingError(RuntimeError):
    """Raised when embeddings could not be produced by the requested provider."""


def _cache_key(model: str, text: str) -> Tuple[str, str]:
    """Cache key for one text under one model."""
    return (model, hashlib.sha256(text.encode("utf-8")).hexdigest())


def _cache_get(key: Tuple[str, str]) -> Optional[List[float]]:
    """Return a cached vector and mark it recently used."""
    vector = _EMBED_CACHE.get(key)
    if vector is not None:
        _EMBED_CACHE.move_to_end(key)
    return vector


def _cache_put(key: Tuple[str, str], vector: List[float]) -> None:
    """Store a vector, evicting the least recently used entry when full."""
    _EMBED_CACHE[key] = vector
    _EMBED_CACHE.move_to_end(key)
    while len(_EMBED_CACHE) > _EMBED_CACHE_MAX:
        _EMBED_CACHE.popitem(last=False)


def clear_embedding_cache() -> None:
    """Clear the in-process embedding cache (tests / model migration)."""
    _EMBED_CACHE.clear()


def _provider() -> str:
    """Return the configured embedding provider: 'openrouter' or 'local'."""
    return getattr(compliance_settings, "embedding_provider", "openrouter")


def _configured_model() -> str:
    """Return the configured OpenRouter embedding model."""
    return getattr(compliance_settings, "embedding_model", DEFAULT_EMBEDDING_MODEL)


def _post_embeddings_batch(texts: List[str], model: str) -> List[List[float]]:
    """POST one batch of texts to OpenRouter with retry/backoff.

    Retries rate limits and transient server errors; fails fast on 4xx that
    indicate a permanent problem (bad model name, unauthorized, oversized input).
    """
    import httpx

    from agent_api.config import settings

    url = f"{settings.openrouter_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}

    last_error: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code in RETRYABLE_STATUSES:
                raise EmbeddingError(
                    f"OpenRouter embeddings returned retryable status {response.status_code}: {response.text[:200]}"
                )
            response.raise_for_status()
            data = response.json()
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            if len(embeddings) != len(texts):
                raise EmbeddingError(
                    f"OpenRouter returned {len(embeddings)} embeddings for {len(texts)} inputs"
                )
            return [e["embedding"] for e in embeddings]
        except EmbeddingError as exc:
            last_error = exc
        except Exception as exc:  # transport errors, timeouts, malformed payloads
            last_error = exc

        if attempt < MAX_RETRIES - 1:
            delay = BASE_BACKOFF_SECONDS * (2 ** attempt) + random.uniform(0, 0.5)
            logger.warning(
                "Embedding batch failed (attempt %d/%d): %s — retrying in %.1fs",
                attempt + 1, MAX_RETRIES, last_error, delay,
            )
            time.sleep(delay)

    raise EmbeddingError(f"OpenRouter embeddings failed after {MAX_RETRIES} attempts: {last_error}")


def _embed_with_cache(
    texts: List[str],
    cache_model: str,
    embed_missing,
) -> List[List[float]]:
    """Embed with per-text caching; only cache misses hit the provider.

    Args:
        texts: Input texts, order preserved.
        cache_model: Model identity used as part of the cache key.
        embed_missing: Callable that embeds a list of uncached texts.
    """
    keys = [_cache_key(cache_model, t) for t in texts]
    results: List[Optional[List[float]]] = [None] * len(texts)
    missing: List[int] = []

    for i, key in enumerate(keys):
        cached = _cache_get(key)
        if cached is not None:
            results[i] = cached
        else:
            missing.append(i)

    if missing:
        vectors = embed_missing([texts[i] for i in missing])
        if len(vectors) != len(missing):
            raise EmbeddingError(
                f"Provider returned {len(vectors)} vectors for {len(missing)} inputs"
            )
        for i, vector in zip(missing, vectors):
            _cache_put(keys[i], vector)
            results[i] = vector

    return [v for v in results if v is not None]


def _openrouter_embed(texts: List[str], model: str, batch_size: int = DEFAULT_BATCH_SIZE) -> List[List[float]]:
    """Embed texts via OpenRouter in bounded batches, preserving input order."""

    def embed_missing(missing: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for start in range(0, len(missing), batch_size):
            batch = missing[start:start + batch_size]
            vectors.extend(_post_embeddings_batch(batch, model))
        return vectors

    return _embed_with_cache(texts, model, embed_missing)


# Lazy-loaded local model
_local_model = None
_local_model_name: str = LOCAL_EMBEDDING_MODEL


def _local_embed(texts: List[str], model_name: str) -> List[List[float]]:
    """Embed texts using local sentence-transformers, with caching."""
    global _local_model, _local_model_name

    if model_name != _local_model_name or _local_model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "Local embeddings require the 'local' extra. "
                "Install with: uv sync --extra local"
            ) from exc
        logger.info("Loading local embedding model: %s", model_name)
        _local_model = SentenceTransformer(model_name)
        _local_model_name = model_name

    model = _local_model

    def embed_missing(missing: List[str]) -> List[List[float]]:
        vectors = model.encode(missing, normalize_embeddings=True, show_progress_bar=False)
        return [v.tolist() for v in vectors]

    return _embed_with_cache(texts, model_name, embed_missing)


def embed_texts(
    texts: List[str],
    model: Optional[str] = None,
    provider: Optional[str] = None,
    *,
    allow_fallback: bool = False,
) -> List[List[float]]:
    """Embed a list of texts and return list of float vectors.

    Never returns vectors from an unrequested model unless `allow_fallback` is
    explicitly set, because mixing embedding spaces corrupts retrieval.

    Args:
        texts: Input texts to embed.
        model: Override model name. Defaults to config value.
        provider: Override provider ('openrouter' or 'local'). Defaults to config.
        allow_fallback: If True, a failed OpenRouter call degrades to the local
            384-dim model. Only safe when the caller targets a 384-dim
            collection. Defaults to False (raise instead).

    Returns:
        List of embedding vectors, in the same order as `texts`.

    Raises:
        EmbeddingError: If the requested provider could not produce vectors and
            fallback was not allowed.
    """
    if not texts:
        return []

    prov = provider or _provider()
    mdl = model or _configured_model()

    if prov == "local":
        return _local_embed(texts, mdl or LOCAL_EMBEDDING_MODEL)

    try:
        return _openrouter_embed(texts, mdl)
    except Exception as exc:
        if not allow_fallback:
            raise EmbeddingError(
                f"OpenRouter embeddings failed for model {mdl}: {exc}. "
                "Refusing to silently switch embedding models (dimension/space mismatch). "
                "Pass allow_fallback=True only if the target collection is 384-dim."
            ) from exc
        logger.warning("OpenRouter embedding failed (%s) — explicit fallback to local model", exc)
        return _local_embed(texts, LOCAL_EMBEDDING_MODEL)


def embed_single(text: str, model: Optional[str] = None, provider: Optional[str] = None) -> List[float]:
    """Embed a single text and return a float vector."""
    result = embed_texts([text], model, provider)
    return result[0] if result else []


def embedding_dim(model: Optional[str] = None, provider: Optional[str] = None) -> int:
    """Return the embedding dimension for the configured model.

    Uses the known-dimension table where possible so this does not require
    downloading a model just to learn its size.
    """
    prov = provider or _provider()
    mdl = model or _configured_model()
    if prov == "local":
        mdl = mdl or LOCAL_EMBEDDING_MODEL
    if mdl in KNOWN_DIMENSIONS:
        return KNOWN_DIMENSIONS[mdl]
    if prov == "local":
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(mdl).get_sentence_embedding_dimension()
    raise EmbeddingError(
        f"Unknown embedding dimension for model {mdl}; add it to KNOWN_DIMENSIONS."
    )
