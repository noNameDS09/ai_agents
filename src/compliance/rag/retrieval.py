"""Qdrant-based retrieval for regulatory chunks.

Provides upsert and search operations partitioned by org_id for tenant isolation.

Collections are named by embedding dimension (e.g. ``compliance_chunks_2048``)
so switching embedding providers cannot mix vector spaces in one collection.
That matters: 384-dim local vectors and 2048-dim OpenRouter vectors are not
comparable, and silently mixing them corrupts retrieval (and therefore
citations).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from .chunking import Chunk
from .embeddings import embed_texts, embedding_dim
from ..config import compliance_settings

logger = logging.getLogger("compliance.rag.retrieval")

# Namespace for deterministic point IDs. Point IDs are derived from
# (regulation_version_id, chunk_index) so re-indexing overwrites in place
# instead of duplicating vectors (duplicates would surface twice in results).
POINT_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def current_embedding_dim() -> int:
    """Dimension of the embeddings this process will produce."""
    try:
        return embedding_dim()
    except Exception:
        # Unknown model: trust explicit config rather than guessing.
        return compliance_settings.embedding_dim


def collection_name() -> str:
    """Dimension-scoped collection name for the configured embedding model."""
    return f"{compliance_settings.qdrant_collection}_{current_embedding_dim()}"


def _point_id(regulation_version_id: uuid.UUID, chunk_index: int) -> str:
    """Stable Qdrant point ID for a chunk within a regulation version."""
    return str(uuid.uuid5(POINT_ID_NAMESPACE, f"{regulation_version_id}:{chunk_index}"))


def get_qdrant_client() -> QdrantClient:
    """Get a Qdrant client (lazy, reused)."""
    return QdrantClient(url=compliance_settings.qdrant_url)


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Create the collection for the active embedding dimension if missing."""
    if client is None:
        client = get_qdrant_client()
    name = collection_name()
    collections = [c.name for c in client.get_collections().collections]
    if name in collections:
        return
    try:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=current_embedding_dim(), distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", name)
    except Exception as exc:
        # Another worker may have created it between the check and the create.
        collections = [c.name for c in client.get_collections().collections]
        if name not in collections:
            raise
        logger.debug("Collection %s already exists (%s)", name, exc)


def upsert_chunks(
    chunks: List[Chunk],
    regulation_version_id: uuid.UUID,
    org_id: Optional[uuid.UUID] = None,
    client: Optional[QdrantClient] = None,
    embeddings: Optional[List[List[float]]] = None,
) -> int:
    """Embed and upsert chunks into Qdrant. Returns number of points upserted.

    Args:
        chunks: Chunks to store.
        regulation_version_id: Owning regulation version (used in payload + IDs).
        org_id: Optional tenant scope for private documents.
        client: Optional Qdrant client (created if omitted).
        embeddings: Precomputed vectors. If omitted, chunks are embedded here.
    """
    if client is None:
        client = get_qdrant_client()
    ensure_collection(client)

    texts = [c.text for c in chunks]
    if embeddings is None:
        embeddings = embed_texts(texts)
    if len(embeddings) != len(chunks):
        raise ValueError(
            f"Got {len(embeddings)} embeddings for {len(chunks)} chunks"
        )

    # Guard: never write vectors that do not match the collection dimension.
    # A mismatch means a different embedding model produced them, and mixing
    # vector spaces silently degrades retrieval (wrong citations).
    expected_dim = current_embedding_dim()
    if embeddings and len(embeddings[0]) != expected_dim:
        raise ValueError(
            f"Embedding dimension {len(embeddings[0])} does not match collection "
            f"{collection_name()} dimension {expected_dim}. Refusing to upsert."
        )

    points = []
    for chunk, emb in zip(chunks, embeddings):
        payload = {
            "regulation_version_id": str(regulation_version_id),
            "chunk_index": chunk.index,
            "text": chunk.text,
            "char_start": chunk.char_start,
            "char_end": chunk.char_end,
            "token_count": chunk.token_count,
        }
        if org_id:
            payload["org_id"] = str(org_id)

        points.append(PointStruct(
            id=_point_id(regulation_version_id, chunk.index),
            vector=emb,
            payload=payload,
        ))

    client.upsert(collection_name=collection_name(), points=points)
    logger.info("Upserted %d chunks for version %s", len(points), regulation_version_id)
    return len(points)


def delete_version_points(
    regulation_version_id: uuid.UUID,
    client: Optional[QdrantClient] = None,
) -> None:
    """Remove all vectors for a regulation version (safe no-op if unindexed)."""
    from qdrant_client.models import FilterSelector

    if client is None:
        client = get_qdrant_client()
    try:
        client.delete(
            collection_name=collection_name(),
            points_selector=FilterSelector(
                filter=Filter(must=[
                    FieldCondition(
                        key="regulation_version_id",
                        match=MatchValue(value=str(regulation_version_id)),
                    )
                ])
            ),
        )
    except Exception as exc:  # collection may not exist yet
        logger.warning("Could not purge vectors for version %s: %s", regulation_version_id, exc)


def search_chunks(
    query: str,
    top_k: int = 5,
    org_id: Optional[uuid.UUID] = None,
    regulation_version_id: Optional[uuid.UUID] = None,
    client: Optional[QdrantClient] = None,
) -> List[dict]:
    """Search Qdrant for chunks similar to the query.

    Returns list of dicts with: text, score, regulation_version_id, chunk_index, char_start, char_end.
    """
    if client is None:
        client = get_qdrant_client()

    query_embedding = embed_texts([query])[0]

    # Build filter
    conditions = []
    if org_id:
        conditions.append(FieldCondition(key="org_id", match=MatchValue(value=str(org_id))))
    if regulation_version_id:
        conditions.append(FieldCondition(
            key="regulation_version_id",
            match=MatchValue(value=str(regulation_version_id)),
        ))

    query_filter = Filter(must=conditions) if conditions else None

    results = client.search(
        collection_name=collection_name(),
        query_vector=query_embedding,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    return [
        {
            "text": r.payload.get("text", ""),
            "score": r.score,
            "regulation_version_id": r.payload.get("regulation_version_id"),
            "chunk_index": r.payload.get("chunk_index"),
            "char_start": r.payload.get("char_start"),
            "char_end": r.payload.get("char_end"),
        }
        for r in results
    ]


async def asearch_chunks(
    query: str,
    top_k: int = 5,
    org_id: Optional[uuid.UUID] = None,
    regulation_version_id: Optional[uuid.UUID] = None,
) -> List[dict]:
    """Async wrapper around `search_chunks` for use in request handlers.

    Embedding + Qdrant search are blocking calls; running them in a worker
    thread keeps the event loop responsive.
    """
    return await asyncio.to_thread(
        search_chunks,
        query,
        top_k,
        org_id,
        regulation_version_id,
    )
