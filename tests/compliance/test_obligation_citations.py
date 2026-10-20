"""Tests for deterministic obligation citation resolution.

The LLM often returns section numbers or prose instead of chunk indices; these
tests pin the deterministic fallbacks that keep every stored obligation cited.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from compliance.agents.obligation_mapping import ObligationMappingAgent


@dataclass
class FakeChunk:
    text: str


def _setup(texts):
    chunks = [FakeChunk(text=t) for t in texts]
    chunk_ids = [str(uuid.uuid4()) for _ in chunks]
    chunk_map = {i: cid for i, cid in enumerate(chunk_ids)}
    return chunks, chunk_ids, chunk_map


def test_explicit_integer_index_resolves():
    chunks, ids, cmap = _setup(["alpha text", "beta text"])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {"citation_chunk_ids": [1], "normalized_text": "x"}, chunks, cmap, ids
    )
    assert result == [ids[1]]


def test_digit_string_index_resolves():
    chunks, ids, cmap = _setup(["alpha", "beta"])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {"citation_chunk_ids": ["0"], "normalized_text": "x"}, chunks, cmap, ids
    )
    assert result == [ids[0]]


def test_uuid_string_resolves():
    chunks, ids, cmap = _setup(["alpha"])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {"citation_chunk_ids": [ids[0]], "normalized_text": "x"}, chunks, cmap, ids
    )
    assert result == [ids[0]]


def test_section_number_in_citation_maps_to_chunk():
    chunks, ids, cmap = _setup([
        "Unrelated preamble about filings.",
        "§ 1022.210(a) Each money services business shall maintain an AML program.",
        "§ 1022.320 Reports by money services businesses.",
    ])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {"citation": "§ 1022.210(a)", "citation_chunk_ids": ["§ 1022.210(a)"], "normalized_text": "maintain program"},
        chunks, cmap, ids,
    )
    assert result == [ids[1]]


def test_section_match_returns_all_matching_chunks():
    chunks, ids, cmap = _setup([
        "§ 1022.210(a) first paragraph",
        "§ 1022.210(b) second paragraph",
        "§ 1022.320 unrelated",
    ])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {"citation": "§ 1022.210", "citation_chunk_ids": [], "normalized_text": "maintain program"},
        chunks, cmap, ids,
    )
    assert set(result) == {ids[0], ids[1]}


def test_lexical_overlap_fallback():
    chunks, ids, cmap = _setup([
        "The weather is pleasant today and unrelated words appear here.",
        "Each licensee must maintain a surety bond and file annual reports.",
    ])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {
            "citation": "unspecified",
            "citation_chunk_ids": [],
            "normalized_text": "Must maintain a surety bond and file annual reports",
        },
        chunks, cmap, ids,
    )
    assert result == [ids[1]]


def test_no_justifiable_match_returns_empty():
    chunks, ids, cmap = _setup([
        "Completely unrelated cooking instructions for pasta.",
    ])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {
            "citation": "unspecified",
            "citation_chunk_ids": [],
            "normalized_text": "quantum entanglement calibration",
        },
        chunks, cmap, ids,
    )
    assert result == []


def test_bogus_explicit_reference_falls_through_to_section_match():
    chunks, ids, cmap = _setup([
        "§ 1022.380(b)(5) A money services business shall file a registration.",
    ])
    result = ObligationMappingAgent._resolve_citation_chunks(
        {
            "citation": "§ 1022.380(b)(5)",
            "citation_chunk_ids": ["Section 1022.380", 999],
            "normalized_text": "file registration",
        },
        chunks, cmap, ids,
    )
    assert result == [ids[0]]
