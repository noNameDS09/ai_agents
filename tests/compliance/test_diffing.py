"""Tests for Phase 2 services: diffing, source fetching, ingest pipeline."""

from __future__ import annotations

import hashlib

from compliance.services.diffing import (
    content_sha256,
    detect_change,
    diff_texts,
)


def test_content_sha256_deterministic():
    assert content_sha256("hello") == hashlib.sha256(b"hello").hexdigest()
    assert content_sha256("hello") == content_sha256("hello")


def test_detect_change_no_previous():
    result = detect_change("new text", None)
    assert result.changed is True
    assert result.old_sha256 is None
    assert result.summary.startswith("Initial version")


def test_detect_change_same_content():
    text = "identical text"
    sha = content_sha256(text)
    result = detect_change(text, sha)
    assert result.changed is False
    assert result.similarity_ratio == 1.0
    assert "No changes" in result.summary


def test_detect_change_different_content():
    old_sha = content_sha256("old text")
    result = detect_change("completely different", old_sha)
    assert result.changed is True
    assert result.old_sha256 == old_sha


def test_diff_texts_minor():
    old = "Line one\nLine two\nLine three\nLine four\nLine five"
    new = "Line one\nLine two\nLine three\nLine four\nLine five (updated)"
    result = diff_texts(old, new)
    assert result.changed is True
    assert result.lines_added >= 1
    assert result.lines_removed >= 1
    assert result.similarity_ratio > 0.5


def test_diff_texts_major_rewrite():
    old = "\n".join(f"Line {i}" for i in range(20))
    new = "\n".join(f"Completely different line {i}" for i in range(20))
    result = diff_texts(old, new)
    assert result.changed is True
    assert result.similarity_ratio < 0.5
    assert "major rewrite" in result.summary


def test_diff_texts_unified_diff_present():
    old = "alpha\nbeta"
    new = "alpha\ngamma"
    result = diff_texts(old, new)
    assert "alpha" in result.unified_diff
    assert "gamma" in result.unified_diff