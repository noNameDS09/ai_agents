"""Obligation Mapping Agent — maps legal requirements to company obligations.

Given a RegulationVersion, uses an LLM to extract discrete obligations, then
always proposes them as POTENTIALLY_RELEVANT (never CONFIRMED — only human
approval promotes them). Every proposed obligation carries citation chunk IDs.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import AgentContract, AgentContext
from ..models.organization import Jurisdiction, LegalEntity
from ..models.regulatory import Obligation, RegulationVersion

logger = logging.getLogger("compliance.agents.obligation_mapping")


class ObligationMappingInput(BaseModel):
    regulation_version_id: str
    org_id: str
    entity_ids: list[str] = Field(default_factory=list)
    prefer_tavily: bool = False


class ProposedObligation(BaseModel):
    citation: str
    normalized_text: str
    citation_chunk_ids: list[str] = Field(default_factory=list)


class ObligationMappingOutput(BaseModel):
    regulation_version_id: str
    obligations_proposed: int = 0
    skipped_uncited: int = 0
    obligations: list[ProposedObligation] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)


OBLIGATION_EXTRACTION_PROMPT = """You extract discrete legal obligations from regulatory text.

Given the regulatory text below, identify each distinct obligation the company
must satisfy. For each obligation:
- Return a short citation (section number / paragraph reference)
- Return a normalized statement of the obligation in plain language
- Cite the exact passage (chunk index) that supports it

Regulatory text:
---
{regulation_text}
---

Respond with JSON only:
{{
  "obligations": [
    {{"citation": "Section 5.2", "normalized_text": "Must maintain a surety bond of at least $X", "citation_chunk_ids": [3]}}
  ]
}}

Rules:
- Only obligations that are clearly stated in the text
- Each obligation must be independently actionable
- citation_chunk_ids MUST be integer chunk numbers from the [CHUNK n] markers above
  (e.g. [0] -> 0), not section numbers and not UUIDs
- If you are uncertain, still include it — it will be reviewed by a human
- Do NOT mark anything as confirmed; all obligations start as potentially relevant
"""


class ObligationMappingAgent(AgentContract):
    name = "obligation_mapping"
    input_schema = ObligationMappingInput
    output_schema = ObligationMappingOutput
    tool_allowlist = frozenset()  # no external tools; LLM does the extraction
    requires_approval = True
    max_retries = 2

    def _get_llm(self):
        from langchain_openai import ChatOpenAI
        from agent_api.config import settings
        return ChatOpenAI(
            model=settings.openrouter_model,
            openai_api_key=settings.openrouter_api_key,
            openai_api_base=settings.openrouter_base_url,
            temperature=0,
        )

    async def run(self, input_data: ObligationMappingInput, ctx: AgentContext) -> ObligationMappingOutput:
        session: AsyncSession = ctx.db_session
        org_id = uuid.UUID(input_data.org_id)

        # Load the regulation version
        rv = await session.get(RegulationVersion, uuid.UUID(input_data.regulation_version_id))
        if rv is None:
            raise ValueError(f"RegulationVersion {input_data.regulation_version_id} not found")

        # Load chunks for citation resolution
        from ..models.regulatory import RegulationChunk
        chunk_result = await session.execute(
            select(RegulationChunk)
            .where(RegulationChunk.regulation_version_id == rv.id)
            .order_by(RegulationChunk.chunk_index)
        )
        chunks = chunk_result.scalars().all()
        chunk_texts = [c.text for c in chunks]
        chunk_ids = [str(c.id) for c in chunks]

        # Build the prompt with chunk index mapping
        chunk_map = {i: cid for i, cid in enumerate(chunk_ids)}
        chunked_text = "\n\n".join(
            f"[CHUNK {i}]\n{c.text}" for i, c in enumerate(chunks)
        ) if chunks else rv.raw_text

        prompt = OBLIGATION_EXTRACTION_PROMPT.format(
            regulation_text=chunked_text[:30000],  # cap to avoid token limits
        )

        # Call LLM
        llm = self._get_llm()
        response = await llm.ainvoke(prompt)

        # Parse the response
        parsed = self._parse_response(response.content)

        # Persist proposed obligations (always POTENTIALLY_RELEVANT)
        proposed = []
        skipped_uncited = 0
        for item in parsed.get("obligations", []):
            citation = item.get("citation", "")
            normalized_text = item.get("normalized_text", "")
            if not normalized_text:
                continue

            cited_chunk_ids = self._resolve_citation_chunks(
                item, chunks, chunk_map, chunk_ids
            )
            if not cited_chunk_ids:
                # An obligation with no supporting passage is not reviewable in
                # a compliance context; do not persist an uncited assertion.
                skipped_uncited += 1
                logger.warning(
                    "Skipping uncited obligation %r (no chunk matched)", citation
                )
                continue

            obligation = Obligation(
                org_id=org_id,
                regulation_version_id=rv.id,
                citation=citation,
                normalized_text=normalized_text,
                applicability="POTENTIALLY_RELEVANT",
                status="DRAFT",
                citation_chunk_ids=cited_chunk_ids,
                created_by=uuid.UUID(ctx.user_id) if ctx.user_id else None,
            )
            session.add(obligation)
            await session.flush()

            proposed.append(ProposedObligation(
                citation=citation,
                normalized_text=normalized_text,
                citation_chunk_ids=cited_chunk_ids,
            ))

        await session.flush()

        return ObligationMappingOutput(
            regulation_version_id=str(rv.id),
            obligations_proposed=len(proposed),
            skipped_uncited=skipped_uncited,
            obligations=proposed,
            citations=[rv.source_url] if rv.source_url else [],
        )

    @staticmethod
    def _resolve_citation_chunks(
        item: dict,
        chunks: list,
        chunk_map: dict[int, str],
        chunk_ids: list[str],
    ) -> list[str]:
        """Resolve an obligation to concrete chunk IDs, deterministically.

        The LLM is unreliable about citing chunk indices. Resolution order:
          1. Valid indices/UUIDs it did return.
          2. Section number in its citation (e.g. "§ 1022.210") found in chunk
             text — this is the strongest deterministic signal.
          3. Highest lexical overlap between the obligation and a chunk, with a
             minimum score so unrelated chunks are not attached.

        Returns [] when nothing can be justified; the caller then drops the
        obligation rather than storing an unsupported claim.
        """
        import re

        # 1. Explicit references from the model.
        resolved: list[str] = []
        for ref in item.get("citation_chunk_ids", []) or []:
            if isinstance(ref, bool):
                continue
            if isinstance(ref, int) and ref in chunk_map:
                resolved.append(chunk_map[ref])
            elif isinstance(ref, str):
                token = ref.strip()
                if token.isdigit() and int(token) in chunk_map:
                    resolved.append(chunk_map[int(token)])
                elif token in chunk_ids:
                    resolved.append(token)
        if resolved:
            return list(dict.fromkeys(resolved))

        # 2. Section number from the citation string.
        citation = item.get("citation", "") or ""
        section = re.search(r"(\d+\.\d+)", citation)
        if section:
            needle = section.group(1)
            matched = [
                chunk_ids[i] for i, c in enumerate(chunks) if needle in c.text
            ]
            if matched:
                return list(dict.fromkeys(matched))

        # 3. Lexical overlap fallback.
        stop = {
            "must", "shall", "with", "that", "this", "from", "have", "been",
            "their", "which", "including", "such", "other", "each", "under",
            "required", "require", "requirements", "reasonably", "effective",
        }
        terms = {
            w for w in re.findall(r"[a-z]{5,}", (item.get("normalized_text") or "").lower())
            if w not in stop
        }
        if not terms:
            return []
        best_index, best_score = -1, 0
        for i, c in enumerate(chunks):
            words = set(re.findall(r"[a-z]{5,}", c.text.lower()))
            score = len(terms & words)
            if score > best_score:
                best_index, best_score = i, score
        # Require a real overlap (>= 3 shared significant words).
        if best_index >= 0 and best_score >= 3:
            return [chunk_ids[best_index]]
        return []

    def _parse_response(self, content: str) -> dict:
        """Parse LLM JSON response, stripping code fences if present."""
        text = content.strip()
        if text.startswith("```"):
            # Remove code fences
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse obligation extraction response: %s", text[:200])
            return {"obligations": []}

    def validate_output(self, output: ObligationMappingOutput) -> list[str]:
        errors = []
        for o in output.obligations:
            if not o.normalized_text.strip():
                errors.append(f"Obligation {o.citation} has empty normalized_text")
            if not o.citation_chunk_ids:
                errors.append(f"Obligation {o.citation} has no citation chunks")
        return errors