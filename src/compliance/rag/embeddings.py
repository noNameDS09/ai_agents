"""Local embedding provider using sentence-transformers.

Uses all-MiniLM-L6-v2 (384-dim) by default. Runs on CPU, no API key needed.
Embeddings are computed locally — no data leaves the server.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger("compliance.rag.embeddings")

# Lazy-loaded model
_model = None
_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"


def get_model(model_name: Optional[str] = None):
    """Load the sentence-transformers model (lazy, cached)."""
    global _model, _model_name
    if model_name and model_name != _model_name:
        _model = None
        _model_name = model_name
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading embedding model: %s", _model_name)
        _model = SentenceTransformer(_model_name)
        logger.info("Embedding model loaded (dim=%d)", _model.get_sentence_embedding_dimension())
    return _model


def embed_texts(texts: List[str], model_name: Optional[str] = None) -> List[List[float]]:
    """Embed a list of texts and return list of float vectors."""
    if not texts:
        return []
    model = get_model(model_name)
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


def embed_single(text: str, model_name: Optional[str] = None) -> List[float]:
    """Embed a single text and return a float vector."""
    result = embed_texts([text], model_name)
    return result[0] if result else []

def embedding_dim(model_name: Optional[str] = None) -> int:
    """Return the embedding dimension for the loaded model."""
    model = get_model(model_name)
    return model.get_sentence_embedding_dimension()