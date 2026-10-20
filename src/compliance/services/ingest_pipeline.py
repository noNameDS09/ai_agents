"""Regulatory ingest pipeline — chunk → embed → store.

Deterministic chunking (no LLM), OpenRouter embeddings, Qdrant storage.
Chunks are linked back to their RegulationVersion for citation resolution.

The pipeline is idempotent: re-running it replaces the version's vectors
(deterministic point IDs + purge) rather than duplicating them.

Index state is recorded on the version (`index_status`) so a failed embedding
call is visible and retryable, instead of leaving a silently unsearchable
regulation in the corpus.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.regulatory import RegulationChunk, RegulationVersion
from ..rag.chunking import Chunk, chunk_text
from ..rag.embeddings import embed_texts
from ..rag.retrieval import delete_version_points, ensure_collection, upsert_chunks

logger = logging.getLogger("compliance.services.ingest_pipeline")

DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64


@dataclass
class IngestResult:
    regulation_version_id: uuid.UUID
    chunks_created: int
    embeddings_upserted: int
    index_status: str


async def ingest_regulation_version(
    session: AsyncSession,
    regulation_version_id: uuid.UUID,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> IngestResult:
    """Chunk, embed, and store a regulation version for RAG retrieval."""
    rv = await session.get(RegulationVersion, regulation_version_id)
    if rv is None:
        raise ValueError(f"RegulationVersion {regulation_version_id} not found")

    # Deterministic chunking
    chunks: List[Chunk] = chunk_text(rv.raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if not chunks:
        logger.warning("No chunks produced for regulation version %s", regulation_version_id)
        rv.index_status = "FAILED"
        rv.index_error = "Chunker produced no chunks (empty raw_text?)"
        await session.flush()
        return IngestResult(regulation_version_id, 0, 0, "FAILED")

    try:
        # Persist chunk metadata in Postgres (idempotent on re-ingest)
        existing_result = await session.execute(
            select(RegulationChunk.chunk_index).where(
                RegulationChunk.regulation_version_id == regulation_version_id
            )
        )
        existing_indices = {row[0] for row in existing_result.all()}

        for chunk in chunks:
            if chunk.index not in existing_indices:
                session.add(RegulationChunk(
                    regulation_version_id=regulation_version_id,
                    chunk_index=chunk.index,
                    text=chunk.text,
                    token_count=chunk.token_count,
                    char_start=chunk.char_start,
                    page_ref=None,
                ))
        await session.flush()

        # Embed all chunks in one call (internally batched + retried). Do this
        # before touching Qdrant so a failure leaves the old vectors intact.
        # Both the embedding call and Qdrant writes are blocking network I/O, so
        # they run in worker threads — otherwise they would stall the event loop
        # (and thus every other request) for the whole 60s+ embedding call.
        texts = [c.text for c in chunks]
        embeddings = await asyncio.to_thread(embed_texts, texts)

        def _store_vectors() -> int:
            from qdrant_client import QdrantClient
            from ..config import compliance_settings
            client = QdrantClient(url=compliance_settings.qdrant_url)
            ensure_collection(client)
            # Replace any previous vectors for this version (chunk size changes
            # can reduce the chunk count; stale points must not survive).
            delete_version_points(regulation_version_id, client=client)
            return upsert_chunks(
                chunks,
                regulation_version_id,
                client=client,
                embeddings=embeddings,
            )

        upserted = await asyncio.to_thread(_store_vectors)

        rv.index_status = "INDEXED"
        rv.index_error = None
        from ..rag.retrieval import collection_name
        rv.index_collection = collection_name()
        await session.flush()

    except Exception as exc:
        rv.index_status = "FAILED"
        rv.index_error = str(exc)[:2000]
        await session.flush()
        logger.error("Indexing failed for regulation version %s: %s", regulation_version_id, exc)
        raise

    return IngestResult(regulation_version_id, len(chunks), upserted, "INDEXED")
