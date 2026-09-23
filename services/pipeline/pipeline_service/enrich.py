"""Enrich: draft a full knowledge object for a candidate via an LLM call.

Grounded by repo_context's grep snippets (see that module's docstring for
why this isn't real RAG). tool_use forces structured output, same pattern
as game-service's AnthropicJudgePort — no free-text JSON to parse or fail
on.
"""

from __future__ import annotations

from anthropic import AsyncAnthropic
from anthropic.types import ToolParam

from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024

SYSTEM_PROMPT = (
    "You are drafting a knowledge-object entry for a technical flashcard "
    "game (Term Rush). The player sees a term and must explain it; your "
    "draft is what an editor reviews before it becomes a live flashcard. "
    "Ground your definition and example in the actual repository usage "
    "snippets provided — cite what this specific codebase does with the "
    "term, not a generic textbook definition. If no usage snippets are "
    "given, write a general but accurate definition instead of inventing "
    "a fake repo-specific detail. "
    "Call draft_term with your entry."
)

DRAFT_TERM_TOOL: ToolParam = {
    "name": "draft_term",
    "description": "Submit a drafted knowledge-object entry for review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "expansion": {
                "type": "string",
                "description": "What the term stands for, or its canonical name "
                "if it isn't an acronym.",
            },
            "definitions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 2,
                "description": "1-2 sentence definitions of the concept.",
            },
            "category": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9-]*$",
                "description": "A lowercase-hyphenated category slug, e.g. "
                "'data-engineering', 'web-frameworks', 'orm'.",
            },
            "difficulty": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5,
                "description": "1=trivial to explain, 5=expert-level.",
            },
            "examples": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 2,
                "description": "Concrete examples, grounded in the repo usage "
                "snippets when any were given.",
            },
        },
        "required": ["expansion", "definitions", "category", "difficulty"],
    },
}


def _user_message(candidate: TermCandidate, usage_snippets: tuple[str, ...]) -> str:
    header = f"Term: {candidate.name}\nSource: {candidate.source_type.value}"
    if not usage_snippets:
        return f"{header}\n\nNo repository usage snippets found."
    joined = "\n\n".join(usage_snippets)
    return f"{header}\n\nRepository usage snippets:\n{joined}"


def _term_id(name: str) -> str:
    """A candidate name like 'better-profanity-fast' is already a valid
    term id; anything with characters outside [a-z0-9-] gets normalized.
    """
    return "".join(c if c.isalnum() or c == "-" else "-" for c in name.lower()).strip(
        "-"
    )


class AnthropicEnricher:
    """Drafts an EnrichedTerm for a TermCandidate via the Anthropic API."""

    def __init__(self, client: AsyncAnthropic) -> None:
        self._client = client

    async def enrich(
        self, candidate: TermCandidate, usage_snippets: tuple[str, ...]
    ) -> EnrichedTerm:
        response = await self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[DRAFT_TERM_TOOL],
            tool_choice={"type": "tool", "name": "draft_term"},
            messages=[
                {"role": "user", "content": _user_message(candidate, usage_snippets)}
            ],
        )

        tool_use = next(block for block in response.content if block.type == "tool_use")
        raw = tool_use.input
        assert isinstance(raw, dict)

        return EnrichedTerm(
            id=_term_id(candidate.name),
            term=candidate.name,
            expansion=str(raw["expansion"]),
            definitions=tuple(raw["definitions"]),  # type: ignore  # untyped provider response
            categories=(str(raw["category"]),),
            difficulty=int(raw["difficulty"]),  # type: ignore  # untyped provider response
            examples=tuple(raw.get("examples", ())),  # type: ignore  # untyped provider response
        )
