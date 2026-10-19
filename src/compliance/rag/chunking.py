"""Deterministic text chunker for regulatory documents.

Splits text into overlapping chunks with configurable size. Chunk boundaries
are deterministic (based on character offsets) so re-chunking the same text
produces identical chunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Chunk:
    """A single text chunk with metadata."""
    index: int
    text: str
    char_start: int
    char_end: int
    token_count: int


def chunk_text(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    separator: str = "\n\n",
) -> List[Chunk]:
    """Split text into overlapping chunks.

    Strategy:
    1. Split on `separator` (paragraphs) first.
    2. Accumulate paragraphs until chunk_size is reached.
    3. Overlap: carry the last `chunk_overlap` chars into the next chunk.
    4. Fall back to character-level splitting if a single paragraph exceeds chunk_size.

    Args:
        text: Input text to chunk.
        chunk_size: Target chunk size in characters.
        chunk_overlap: Number of characters to overlap between chunks.
        separator: Primary split separator.

    Returns:
        List of Chunk objects with deterministic indices and offsets.
    """
    if not text or not text.strip():
        return []

    # Normalize whitespace
    text = text.strip()

    # Split into paragraphs
    paragraphs = [p.strip() for p in text.split(separator) if p.strip()]

    chunks: List[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    char_offset = 0

    def _flush(parts: list[str], start: int) -> None:
        nonlocal chunks
        chunk_text = "\n\n".join(parts).strip()
        if not chunk_text:
            return
        chunks.append(Chunk(
            index=len(chunks),
            text=chunk_text,
            char_start=start,
            char_end=start + len(chunk_text),
            token_count=_estimate_tokens(chunk_text),
        ))

    for para in paragraphs:
        # If a single paragraph exceeds chunk_size, split it
        if len(para) > chunk_size:
            # Flush current accumulator first
            if current_parts:
                _flush(current_parts, char_offset - current_len)
                # Carry overlap
                overlap_text = "\n\n".join(current_parts)[-chunk_overlap:]
                current_parts = [overlap_text] if overlap_text.strip() else []
                current_len = len("\n\n".join(current_parts))
            # Split the long paragraph
            for i in range(0, len(para), chunk_size - chunk_overlap):
                sub = para[i:i + chunk_size]
                _flush([sub], char_offset + i)
            char_offset += len(para) + len(separator)
            current_parts = []
            current_len = 0
            continue

        # Would adding this paragraph exceed chunk_size?
        new_len = current_len + len(para) + (2 if current_parts else 0)
        if new_len > chunk_size and current_parts:
            _flush(current_parts, char_offset - current_len)
            # Carry overlap
            overlap_text = "\n\n".join(current_parts)[-chunk_overlap:]
            current_parts = [overlap_text] if overlap_text.strip() else []
            current_len = len("\n\n".join(current_parts))
            char_offset = char_offset  # maintain offset

        current_parts.append(para)
        current_len += len(para) + (2 if len(current_parts) > 1 else 0)
        char_offset += len(para) + len(separator)

    # Flush remaining
    if current_parts:
        _flush(current_parts, max(0, char_offset - current_len))

    # Re-index to ensure sequential
    for i, c in enumerate(chunks):
        c.index = i

    return chunks


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(text) // 4)