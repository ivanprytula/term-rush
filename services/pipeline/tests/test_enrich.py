"""AnthropicEnricher tests.

Uses a stub in place of AsyncAnthropic, same pattern as game-service's
test_llm_judge.py — no network call, no API key needed.
"""

from __future__ import annotations

from typing import Any

import pytest
from anthropic.types import ToolUseBlock

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.enrich import AnthropicEnricher
from pipeline_service.enrich import _term_id


@pytest.fixture
def candidate() -> TermCandidate:
    return TermCandidate(
        name="fastapi",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )


class _FakeResponse:
    def __init__(self, tool_input: dict[str, Any]) -> None:
        self.content = [
            ToolUseBlock(
                type="tool_use", id="toolu_fake", name="draft_term", input=tool_input
            )
        ]


class _FakeMessages:
    def __init__(self, tool_input: dict[str, Any]) -> None:
        self._tool_input = tool_input
        self.last_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_kwargs = kwargs
        return _FakeResponse(self._tool_input)


class _FakeAnthropicClient:
    def __init__(self, tool_input: dict[str, Any]) -> None:
        self.messages = _FakeMessages(tool_input)


def test_term_id_normalizes_a_valid_name() -> None:
    assert _term_id("better-profanity-fast") == "better-profanity-fast"


def test_term_id_strips_invalid_characters() -> None:
    assert _term_id("FastAPI[standard]") == "fastapi-standard"


@pytest.mark.asyncio
async def test_enrich_maps_tool_use_input_to_enriched_term(
    candidate: TermCandidate,
) -> None:
    client = _FakeAnthropicClient(
        {
            "expansion": "FastAPI",
            "definitions": ["A modern Python web framework."],
            "category": "web-frameworks",
            "difficulty": 3,
            "examples": ["Used for services/content's REST API."],
        }
    )
    enricher = AnthropicEnricher(client)  # type: ignore

    result = await enricher.enrich(candidate, usage_snippets=())

    assert result.id == "fastapi"
    assert result.term == "fastapi"
    assert result.expansion == "FastAPI"
    assert result.definitions == ("A modern Python web framework.",)
    assert result.categories == ("web-frameworks",)
    assert result.difficulty == 3
    assert result.examples == ("Used for services/content's REST API.",)


@pytest.mark.asyncio
async def test_enrich_defaults_examples_when_omitted(candidate: TermCandidate) -> None:
    client = _FakeAnthropicClient(
        {
            "expansion": "FastAPI",
            "definitions": ["A framework."],
            "category": "web-frameworks",
            "difficulty": 3,
        }
    )
    enricher = AnthropicEnricher(client)  # type: ignore

    result = await enricher.enrich(candidate, usage_snippets=())

    assert result.examples == ()


@pytest.mark.asyncio
async def test_enrich_passes_usage_snippets_in_the_user_message(
    candidate: TermCandidate,
) -> None:
    client = _FakeAnthropicClient(
        {
            "expansion": "FastAPI",
            "definitions": ["A framework."],
            "category": "web-frameworks",
            "difficulty": 3,
        }
    )
    enricher = AnthropicEnricher(client)  # type: ignore

    await enricher.enrich(candidate, usage_snippets=("app.py:1: import fastapi",))

    assert client.messages.last_kwargs is not None
    user_content = client.messages.last_kwargs["messages"][0]["content"]
    assert "app.py:1: import fastapi" in user_content


@pytest.mark.asyncio
async def test_enrich_notes_absence_of_usage_snippets(
    candidate: TermCandidate,
) -> None:
    client = _FakeAnthropicClient(
        {
            "expansion": "FastAPI",
            "definitions": ["A framework."],
            "category": "web-frameworks",
            "difficulty": 3,
        }
    )
    enricher = AnthropicEnricher(client)  # type: ignore

    await enricher.enrich(candidate, usage_snippets=())

    assert client.messages.last_kwargs is not None
    user_content = client.messages.last_kwargs["messages"][0]["content"]
    assert "No repository usage snippets found" in user_content
