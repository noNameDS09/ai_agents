"""Qdrant-based retrieval for regulatory chunks.

Provides upsert and search operations partitioned by org_id for tenant isolation.
"""

from __future__ import annotations

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

COLLECTION_NAME = compliance_settings.qdrant_collection
QDRANT_URL = compliance_settings.qdrant_url
EMBEDDING_DIM = compliance_settings.embedding_dim


def get_qdrant_client() -> QdrantClient:
    """Get a Qdrant client (lazy, reused)."""
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: Optional[QdrantClient] = None) -> None:
    """Create the collection if it doesn't exist."""
    if client is None:
        client = get_qdrant_client()
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection: %s", COLLECTION_NAME)


def upsert_chunks(
    chunks: List[Chunk],
    regulation_version_id: uuid.UUID,
    org_id: Optional[uuid.UUID] = None,
    client: Optional[QdrantClient] = None,
) -> int:
    """Embed and upsert chunks into Qdrant. Returns number of points upserted."""
    if client is None:
        client = get_qdrant_client()
    ensure_collection(client)

    texts = [c.text for c in chunks]
    embeddings = embed_texts(texts)

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
            id=str(uuid.uuid4()),
            vector=emb,
            payload=payload,
        ))

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    logger.info("Upserted %d chunks for version %s", len(points), regulation_version_id)
    return len(points)


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
        collection_name=COLLECTION_NAME,
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