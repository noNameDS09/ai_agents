"""RegulationVersion, RegulationChunk, and Obligation models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import ComplianceBase, TimestampMixin


class RegulationVersion(ComplianceBase, TimestampMixin):
    __tablename__ = "regulation_versions"
    __table_args__ = (UniqueConstraint("citation", "version_no", name="uq_regulation_version"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jurisdiction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("jurisdictions.id"), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("regulation_versions.id"), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    # PENDING | INDEXED | FAILED — tracks chunk/embed state in the vector store.
    # A version is a valid legal record even if indexing failed; retrieval just
    # cannot cite it until re-indexed.
    index_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    index_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Which embedding-space collection holds this version's vectors, e.g.
    # compliance_chunks_2048. Recorded so a provider/model change is detectable
    # (stale index) instead of silently returning nothing at retrieval time.
    index_collection: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ingested_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    chunks: Mapped[List["RegulationChunk"]] = relationship(back_populates="regulation_version", cascade="all, delete-orphan")
    obligations: Mapped[List["Obligation"]] = relationship(back_populates="regulation_version", cascade="all, delete-orphan")


class RegulationChunk(ComplianceBase):
    __tablename__ = "regulation_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    regulation_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("regulation_versions.id", ondelete="CASCADE"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_ref: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # embedding stored in Qdrant, not Postgres (pgvector not available)

    regulation_version: Mapped["RegulationVersion"] = relationship(back_populates="chunks")


class Obligation(ComplianceBase, TimestampMixin):
    __tablename__ = "obligations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)  # tenant scope
    regulation_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("regulation_versions.id"), nullable=False)
    citation: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    applicability: Mapped[str] = mapped_column(String(30), nullable=False, default="POTENTIALLY_RELEVANT")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    responsible_entity_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    citation_chunk_ids: Mapped[Optional[list]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=True)
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    regulation_version: Mapped["RegulationVersion"] = relationship(back_populates="obligations")