"""Critique node (ADR-0019 Slice 3): the model checks its own draft
against the retrieved context and either accepts it or asks for another
retrieval pass with a refined query. This is the first place in the repo
where the model, not fixed Python, decides whether another retrieval
pass is needed.

refined_query is model-chosen input that re-enters retrieve() as a
search query — ADR-0013's tool-input hardening applies: it is length-
clamped before use (the same "don't trust the schema's advisory bounds"
posture the judge's score-clamping already established), independent of
whatever the schema's maxLength claims.
"""

from __future__ import annotations

from typing import NamedTuple

from anthropic import AsyncAnthropic
from anthropic.types import ToolParam

from pipeline_service.agentic_review.chunk_search import RetrievedChunk
from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 512

REFINED_QUERY_MAX_LEN = 128

SYSTEM_PROMPT = (
    "You are reviewing a drafted knowledge-object entry for a technical "
    "flashcard game, checking it against the retrieved document chunks "
    "that grounded it. Accept the draft if the retrieved chunks support "
    "its definition and example, or if no chunks were relevant enough to "
    "expect better grounding. Reject it and propose a refined search "
    "query only if you believe a different query would surface chunks "
    "that materially improve the draft's accuracy. "
    "Call submit_critique with your decision."
)

CRITIQUE_TOOL: ToolParam = {
    "name": "submit_critique",
    "description": "Submit whether the draft is accepted, or a refined query "
    "to retry retrieval with.",
    "input_schema": {
        "type": "object",
        "properties": {
            "accept": {
                "type": "boolean",
                "description": "True if the draft is well-grounded and ready "
                "for review; false to request another retrieval pass.",
            },
            "refined_query": {
                "type": "string",
                "maxLength": REFINED_QUERY_MAX_LEN,
                "description": "A different search query to retry retrieval "
                "with. Required when accept is false.",
            },
        },
        "required": ["accept"],
    },
}


class Critique(NamedTuple):
    accept: bool
    refined_query: str | None


def _user_message(
    candidate: TermCandidate,
    draft: EnrichedTerm,
    retrieved_chunks: tuple[RetrievedChunk, ...],
) -> str:
    header = f"Term: {candidate.name}"
    draft_block = (
        f"Drafted expansion: {draft.expansion}\n"
        f"Drafted definitions: {'; '.join(draft.definitions)}"
    )
    if not retrieved_chunks:
        chunks_block = "No retrieved document chunks were found."
    else:
        joined = "\n\n".join(
            f"[{chunk.source_file}] {chunk.text}" for chunk in retrieved_chunks
        )
        chunks_block = f"Retrieved document chunks:\n{joined}"
    return f"{header}\n\n{draft_block}\n\n{chunks_block}"


class AgenticCritic:
    """Decides whether a drafted EnrichedTerm is well-grounded, or whether
    another retrieval pass with a refined query is warranted.
    """

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def critique(
        self,
        candidate: TermCandidate,
        draft: EnrichedTerm,
        retrieved_chunks: tuple[RetrievedChunk, ...],
    ) -> Critique:
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[CRITIQUE_TOOL],
            tool_choice={"type": "tool", "name": "submit_critique"},
            messages=[
                {
                    "role": "user",
                    "content": _user_message(candidate, draft, retrieved_chunks),
                }
            ],
        )

        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw = tool_use.input
        assert isinstance(raw, dict)

        accept = bool(raw["accept"])
        if accept:
            return Critique(accept=True, refined_query=None)

        refined_query = str(raw.get("refined_query", "")).strip()[
            :REFINED_QUERY_MAX_LEN
        ]
        if not refined_query:
            # Model rejected without a usable refined query — nothing to
            # retry with, so accept rather than loop on an empty query.
            return Critique(accept=True, refined_query=None)
        return Critique(accept=False, refined_query=refined_query)
