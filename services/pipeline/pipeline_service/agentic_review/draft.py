"""Draft node (ADR-0019 Slice 2): reuses enrich.py's draft_term tool and
forced tool_use pattern, but grounds the prompt in retrieved document
chunks (ADR-0012) instead of repo-grep usage snippets — the difference
between this slice and enriched_candidates is what grounds the draft,
not how the model is asked to produce one.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic

from pipeline_service.agentic_review.chunk_search import RetrievedChunk
from pipeline_service.candidate import TermCandidate
from pipeline_service.enrich import DRAFT_TERM_TOOL
from pipeline_service.enrich import MAX_TOKENS
from pipeline_service.enrich import MODEL
from pipeline_service.enrich import SYSTEM_PROMPT
from pipeline_service.enrich import term_id
from pipeline_service.enriched_term import EnrichedTerm


def _user_message(
    candidate: TermCandidate, retrieved_chunks: tuple[RetrievedChunk, ...]
) -> str:
    header = f"Term: {candidate.name}\nSource: {candidate.source_type.value}"
    if not retrieved_chunks:
        return f"{header}\n\nNo retrieved document chunks found."
    joined = "\n\n".join(
        f"[{chunk.source_file}] {chunk.text}" for chunk in retrieved_chunks
    )
    return f"{header}\n\nRetrieved document chunks:\n{joined}"


class AgenticDrafter:
    """Drafts an EnrichedTerm for a TermCandidate, grounded in retrieved
    document chunks rather than repo usage snippets.
    """

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def draft(
        self, candidate: TermCandidate, retrieved_chunks: tuple[RetrievedChunk, ...]
    ) -> EnrichedTerm:
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[DRAFT_TERM_TOOL],
            tool_choice={"type": "tool", "name": "draft_term"},
            messages=[
                {
                    "role": "user",
                    "content": _user_message(candidate, retrieved_chunks),
                }
            ],
        )

        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw = tool_use.input
        assert isinstance(raw, dict)

        return EnrichedTerm(
            id=term_id(candidate.name),
            term=candidate.name,
            expansion=str(raw["expansion"]),
            definitions=tuple(raw["definitions"]),  # type: ignore  # untyped provider response
            categories=(str(raw["category"]),),
            difficulty=int(raw["difficulty"]),  # type: ignore  # untyped provider response
            examples=tuple(raw.get("examples", ())),  # type: ignore  # untyped provider response
        )
