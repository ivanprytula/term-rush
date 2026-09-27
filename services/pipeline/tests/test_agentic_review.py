"""Tests for the ADR-0019 LangGraph agent slice (Slice 4: retrieve ->
draft -> critique (bounded loop) -> submit_for_review).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from anthropic.types import ToolUseBlock

from pipeline_service.agentic_review.chunk_search import RetrievedChunk
from pipeline_service.agentic_review.chunk_search import search_document_chunks
from pipeline_service.agentic_review.critique import REFINED_QUERY_MAX_LEN
from pipeline_service.agentic_review.critique import AgenticCritic
from pipeline_service.agentic_review.draft import AgenticDrafter
from pipeline_service.agentic_review.graph import MAX_RETRIEVAL_PASSES
from pipeline_service.agentic_review.graph import build_agentic_review_graph
from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm

DRAFT_TOOL_INPUT = {
    "expansion": "FastAPI",
    "definitions": ["A modern Python web framework."],
    "category": "web-frameworks",
    "difficulty": 3,
}


@pytest.fixture
def candidate() -> TermCandidate:
    return TermCandidate(
        name="fastapi",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )


@pytest.fixture
def draft() -> EnrichedTerm:
    return EnrichedTerm(
        id="fastapi",
        term="fastapi",
        expansion="FastAPI",
        definitions=("A modern Python web framework.",),
        categories=("web-frameworks",),
        difficulty=3,
    )


class _FakeResponse:
    def __init__(self, name: str, tool_input: dict[str, Any]) -> None:
        self.content = [
            ToolUseBlock(type="tool_use", id="toolu_fake", name=name, input=tool_input)
        ]


class _FakeMessages:
    """Dispatches by the tool name each call is forced to use, so one fake
    client can stand in for both draft_term and submit_critique calls
    across a single graph run.
    """

    def __init__(self, tool_inputs: dict[str, Any] | list[dict[str, Any]]) -> None:
        self._tool_inputs = tool_inputs
        self._call_index = 0
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        name = kwargs["tool_choice"]["name"]
        if isinstance(self._tool_inputs, list):
            tool_input = self._tool_inputs[self._call_index]
            self._call_index += 1
        else:
            tool_input = self._tool_inputs
        return _FakeResponse(name, tool_input)

    @property
    def last_kwargs(self) -> dict[str, Any] | None:
        return self.calls[-1] if self.calls else None


class _FakeAnthropicClient:
    def __init__(self, tool_inputs: dict[str, Any] | list[dict[str, Any]]) -> None:
        self.messages = _FakeMessages(tool_inputs)


@pytest.mark.asyncio
async def test_search_document_chunks_returns_matches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/document-chunks/search"
        assert request.url.params["query"] == "fastapi"
        return httpx.Response(
            200,
            json={
                "chunks": [
                    {
                        "id": 1,
                        "text": "FastAPI is a web framework.",
                        "source_file": "docs.pdf",
                        "chunk_index": 0,
                        "char_start": 0,
                        "char_end": 28,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chunks = await search_document_chunks(
            client, "http://content-service", "fastapi", top_k=5
        )

    assert len(chunks) == 1
    assert chunks[0].text == "FastAPI is a web framework."
    assert chunks[0].source_file == "docs.pdf"


@pytest.mark.asyncio
async def test_search_document_chunks_returns_empty_on_http_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        chunks = await search_document_chunks(
            client, "http://content-service", "fastapi", top_k=5
        )

    assert chunks == ()


@pytest.mark.asyncio
async def test_agentic_drafter_grounds_in_retrieved_chunks(
    candidate: TermCandidate,
) -> None:
    client = _FakeAnthropicClient(DRAFT_TOOL_INPUT)
    drafter = AgenticDrafter(client)  # type: ignore

    result = await drafter.draft(
        candidate, (RetrievedChunk(text="FastAPI docs snippet", source_file="x.pdf"),)
    )

    assert result.id == "fastapi"
    assert result.expansion == "FastAPI"
    assert client.messages.last_kwargs is not None
    user_content = client.messages.last_kwargs["messages"][0]["content"]
    assert "FastAPI docs snippet" in user_content
    assert "x.pdf" in user_content


@pytest.mark.asyncio
async def test_agentic_drafter_notes_absence_of_retrieved_chunks(
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
    drafter = AgenticDrafter(client)  # type: ignore

    await drafter.draft(candidate, ())

    assert client.messages.last_kwargs is not None
    user_content = client.messages.last_kwargs["messages"][0]["content"]
    assert "No retrieved document chunks found" in user_content


@pytest.mark.asyncio
async def test_critic_accepts_a_well_grounded_draft(
    candidate: TermCandidate, draft: EnrichedTerm
) -> None:
    client = _FakeAnthropicClient({"accept": True})
    critic = AgenticCritic(client)  # type: ignore

    result = await critic.critique(candidate, draft, ())

    assert result.accept is True
    assert result.refined_query is None


@pytest.mark.asyncio
async def test_critic_rejects_with_a_refined_query(
    candidate: TermCandidate, draft: EnrichedTerm
) -> None:
    client = _FakeAnthropicClient(
        {"accept": False, "refined_query": "fastapi dependency injection"}
    )
    critic = AgenticCritic(client)  # type: ignore

    result = await critic.critique(candidate, draft, ())

    assert result.accept is False
    assert result.refined_query == "fastapi dependency injection"


@pytest.mark.asyncio
async def test_critic_accepts_when_rejection_has_no_usable_query(
    candidate: TermCandidate, draft: EnrichedTerm
) -> None:
    """A reject with an empty/missing refined_query has nothing to retry
    with — accept rather than loop forever on an empty query.
    """
    client = _FakeAnthropicClient({"accept": False, "refined_query": "   "})
    critic = AgenticCritic(client)  # type: ignore

    result = await critic.critique(candidate, draft, ())

    assert result.accept is True
    assert result.refined_query is None


@pytest.mark.asyncio
async def test_critic_clamps_an_overlong_refined_query(
    candidate: TermCandidate, draft: EnrichedTerm
) -> None:
    """ADR-0013-style hardening: the schema's maxLength is advisory, not
    enforced by the provider — clamp independently rather than trust it.
    """
    overlong = "x" * (REFINED_QUERY_MAX_LEN * 2)
    client = _FakeAnthropicClient({"accept": False, "refined_query": overlong})
    critic = AgenticCritic(client)  # type: ignore

    result = await critic.critique(candidate, draft, ())

    assert result.refined_query is not None
    assert len(result.refined_query) == REFINED_QUERY_MAX_LEN


def _chunk_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "chunks": [
                {
                    "id": 1,
                    "text": "A chunk.",
                    "source_file": "x.pdf",
                    "chunk_index": 0,
                    "char_start": 0,
                    "char_end": 8,
                }
            ]
        },
    )


def _submission_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/document-chunks/search":
        return _chunk_response()
    assert request.url.path == "/review-queue/candidates"
    return httpx.Response(201, json={"id": 42, "status": "pending"})


def _initial_state(candidate: TermCandidate, query: str = "fastapi") -> dict[str, Any]:
    return {
        "candidate": candidate,
        "query": query,
        "retrieved_chunks": (),
        "draft": None,
        "retrieval_passes": 0,
        "accepted": False,
        "review_candidate_id": None,
    }


@pytest.mark.asyncio
async def test_graph_accepts_on_first_pass_and_submits_for_review(
    candidate: TermCandidate,
) -> None:
    transport = httpx.MockTransport(_submission_handler)
    anthropic_client = _FakeAnthropicClient([DRAFT_TOOL_INPUT, {"accept": True}])

    async with httpx.AsyncClient(transport=transport) as client:
        graph = build_agentic_review_graph(
            client,
            "http://content-service",
            anthropic_client,  # type: ignore
        )
        result = await graph.ainvoke(_initial_state(candidate))

    assert result["draft"] is not None
    assert result["draft"].expansion == "FastAPI"
    assert result["retrieval_passes"] == 1
    assert result["review_candidate_id"] == 42


@pytest.mark.asyncio
async def test_graph_loops_back_to_retrieve_on_rejection(
    candidate: TermCandidate,
) -> None:
    """Reject once with a refined query, accept the second draft — proves
    the model-directed loop actually re-enters retrieve with the refined
    query, not just re-runs with the same one.
    """
    seen_queries: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/document-chunks/search":
            seen_queries.append(request.url.params["query"])
        return _submission_handler(request)

    transport = httpx.MockTransport(handler)
    anthropic_client = _FakeAnthropicClient(
        [
            DRAFT_TOOL_INPUT,
            {"accept": False, "refined_query": "fastapi middleware"},
            DRAFT_TOOL_INPUT,
            {"accept": True},
        ]
    )

    async with httpx.AsyncClient(transport=transport) as client:
        graph = build_agentic_review_graph(
            client,
            "http://content-service",
            anthropic_client,  # type: ignore
        )
        result = await graph.ainvoke(_initial_state(candidate))

    assert result["retrieval_passes"] == 2
    assert seen_queries == ["fastapi", "fastapi middleware"]
    assert result["draft"] is not None
    assert result["review_candidate_id"] == 42


@pytest.mark.asyncio
async def test_graph_stops_at_max_retrieval_passes(candidate: TermCandidate) -> None:
    """A model that never accepts still terminates - the iteration cap
    accepts the last draft rather than looping forever.
    """
    transport = httpx.MockTransport(_submission_handler)
    always_reject = []
    for _ in range(MAX_RETRIEVAL_PASSES):
        always_reject.append(DRAFT_TOOL_INPUT)
        always_reject.append({"accept": False, "refined_query": "another query"})
    anthropic_client = _FakeAnthropicClient(always_reject)

    async with httpx.AsyncClient(transport=transport) as client:
        graph = build_agentic_review_graph(
            client,
            "http://content-service",
            anthropic_client,  # type: ignore
        )
        result = await graph.ainvoke(_initial_state(candidate))

    assert result["retrieval_passes"] == MAX_RETRIEVAL_PASSES
    assert result["accepted"] is True
    assert result["draft"] is not None
    assert result["review_candidate_id"] == 42


@pytest.mark.asyncio
async def test_graph_leaves_review_candidate_id_none_on_rejection(
    candidate: TermCandidate,
) -> None:
    """content-service refusing the submission (e.g. malformed draft)
    doesn't crash the graph — same posture loaded_candidates takes on an
    individual submission's rejection.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/document-chunks/search":
            return _chunk_response()
        return httpx.Response(422, text="Invalid request")

    transport = httpx.MockTransport(handler)
    anthropic_client = _FakeAnthropicClient([DRAFT_TOOL_INPUT, {"accept": True}])

    async with httpx.AsyncClient(transport=transport) as client:
        graph = build_agentic_review_graph(
            client,
            "http://content-service",
            anthropic_client,  # type: ignore
        )
        result = await graph.ainvoke(_initial_state(candidate))

    assert result["review_candidate_id"] is None
