"""Ingest a local regulation file (txt, xml, html) as a RegulationVersion.

Useful for bootstrapping authoritative text that is published as a document
rather than a stable web page (eCFR XML, state statute exports, etc.).

The file is treated as an immutable version: re-running with identical content
is a no-op; changed content creates a new version that supersedes the previous.

Usage:
    uv run python scripts/ingest_regulation_file.py \
        --file /tmp/opencode/ecfr1022.xml \
        --citation "31 CFR Part 1022" \
        --title "Rules for Money Services Businesses" \
        --jurisdiction US-FEDERAL \
        --publisher "FinCEN (eCFR)" \
        --effective-date 2025-01-01
"""

from __future__ import annotations

import argparse
import asyncio
import html
import re
import sys
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select

from agent_api.database import async_session
from compliance.models.organization import Jurisdiction
from compliance.models.regulatory import RegulationVersion
from compliance.services.ingest_pipeline import ingest_regulation_version
from compliance.services.diffing import content_sha256, diff_texts


def strip_markup(raw: str) -> str:
    """Convert XML/HTML to readable plain text.

    Deliberately simple: tags become whitespace, entities are decoded, and
    runs of blank lines are collapsed. Legal structure (section numbers,
    paragraph letters) is preserved in the text itself.
    """
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


async def ingest_file(
    path: Path,
    citation: str,
    title: str,
    jurisdiction_code: str,
    publisher: str | None,
    effective_date: date | None,
) -> None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    text = strip_markup(raw)
    sha = content_sha256(text)

    async with async_session() as session:
        jur = (
            await session.execute(
                select(Jurisdiction).where(Jurisdiction.code == jurisdiction_code)
            )
        ).scalar_one_or_none()
        if jur is None:
            jur = Jurisdiction(
                code=jurisdiction_code,
                name=jurisdiction_code,
                country="US",
                regime="money_transmitter",
            )
            session.add(jur)
            await session.flush()

        prev = (
            await session.execute(
                select(RegulationVersion)
                .where(RegulationVersion.citation == citation)
                .order_by(RegulationVersion.version_no.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if prev is not None and prev.content_sha256 == sha:
            print(f"No change: {citation} v{prev.version_no} is current ({sha[:12]}).")
            return

        version_no = (prev.version_no + 1) if prev else 1
        rv = RegulationVersion(
            jurisdiction_id=jur.id,
            citation=citation,
            title=title,
            source_url=f"file://{path.resolve()}",
            publisher=publisher,
            effective_date=effective_date,
            version_no=version_no,
            supersedes_id=prev.id if prev else None,
            raw_text=text,
            content_sha256=sha,
            index_status="PENDING",
        )
        session.add(rv)
        await session.flush()

        if prev is not None:
            print(f"Change summary: {diff_texts(prev.raw_text, text).summary}")

        result = await ingest_regulation_version(session, rv.id)
        await session.commit()

        print(
            f"Stored {citation} v{version_no} "
            f"({result.chunks_created} chunks, index={result.index_status}, "
            f"version_id={rv.id}, sha256={sha[:12]})"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--citation", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--jurisdiction", default="US-FEDERAL")
    parser.add_argument("--publisher", default=None)
    parser.add_argument("--effective-date", default=None)
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        return 1

    effective = date.fromisoformat(args.effective_date) if args.effective_date else None
    asyncio.run(
        ingest_file(
            path=args.file,
            citation=args.citation,
            title=args.title,
            jurisdiction_code=args.jurisdiction,
            publisher=args.publisher,
            effective_date=effective,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
