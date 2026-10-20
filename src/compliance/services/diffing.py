"""Regulatory version diffing and change detection.

Pure deterministic logic — no LLM involvement.
"""

from __future__ import annotations

import hashlib
import difflib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DiffResult:
    changed: bool
    old_sha256: Optional[str]
    new_sha256: str
    similarity_ratio: float
    lines_added: int
    lines_removed: int
    unified_diff: str = ""
    summary: str = ""


def content_sha256(text: str) -> str:
    """Compute SHA-256 hash of content for dedup and change detection."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_change(
    new_text: str,
    old_sha256: Optional[str],
) -> DiffResult:
    """Detect whether new text differs from the previous version by hash."""
    new_sha = content_sha256(new_text)
    if old_sha256 is None:
        return DiffResult(
            changed=True,
            old_sha256=None,
            new_sha256=new_sha,
            similarity_ratio=0.0,
            lines_added=len(new_text.splitlines()),
            lines_removed=0,
            summary="Initial version (no previous content).",
        )
    if new_sha == old_sha256:
        return DiffResult(
            changed=False,
            old_sha256=old_sha256,
            new_sha256=new_sha,
            similarity_ratio=1.0,
            lines_added=0,
            lines_removed=0,
            summary="No changes detected.",
        )
    return DiffResult(
        changed=True,
        old_sha256=old_sha256,
        new_sha256=new_sha,
        similarity_ratio=0.0,
        lines_added=len(new_text.splitlines()),
        lines_removed=0,
        summary=f"Content changed (new sha256: {new_sha[:12]}).",
    )


def diff_texts(old_text: str, new_text: str) -> DiffResult:
    """Produce a unified diff between two regulation versions."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    ratio = difflib.SequenceMatcher(None, old_lines, new_lines).ratio()

    diff = list(difflib.unified_diff(
        old_lines, new_lines, fromfile="previous", tofile="current", lineterm=""
    ))

    lines_added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    lines_removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))

    summary = f"{lines_added} lines added, {lines_removed} removed. Similarity: {ratio:.2%}"
    if ratio > 0.9:
        summary += " (minor amendment)"
    elif ratio > 0.5:
        summary += " (substantial change)"
    else:
        summary += " (major rewrite)"

    return DiffResult(
        changed=True,
        old_sha256=content_sha256(old_text),
        new_sha256=content_sha256(new_text),
        similarity_ratio=round(ratio, 4),
        lines_added=lines_added,
        lines_removed=lines_removed,
        unified_diff="\n".join(diff),
        summary=summary,
    )