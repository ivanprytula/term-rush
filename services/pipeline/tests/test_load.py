"""Tests for the load stage's content-service submission."""

from __future__ import annotations

import json

import httpx
import pytest

from pipeline_service.candidate import Confidence
from pipeline_service.candidate import SourceType
from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm
from pipeline_service.load import ReviewCandidateRejected
from pipeline_service.load import submit_for_review


@pytest.fixture
def candidate() -> TermCandidate:
    return TermCandidate(
        name="fastapi",
        source_type=SourceType.DEPENDENCY_MANIFEST,
        source_file="pyproject.toml",
        confidence=Confidence.HIGH,
    )


@pytest.fixture
def term() -> EnrichedTerm:
    return EnrichedTerm(
        id="fastapi",
        term="fastapi",
        expansion="FastAPI",
        definitions=("A modern Python web framework.",),
        categories=("web-frameworks",),
        difficulty=3,
    )


@pytest.mark.asyncio
async def test_submit_for_review_returns_the_assigned_id(
    term: EnrichedTerm, candidate: TermCandidate
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/review-queue/candidates"
        payload = json.loads(request.read())
        assert payload["term"]["id"] == "fastapi"
        assert payload["source_type"] == "dependency_manifest"
        return httpx.Response(201, json={"id": 42, "status": "pending"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        candidate_id = await submit_for_review(
            client, "http://content-service", term, candidate
        )

    assert candidate_id == 42


@pytest.mark.asyncio
async def test_submit_for_review_raises_on_4xx(
    term: EnrichedTerm, candidate: TermCandidate
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text="Invalid request")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ReviewCandidateRejected) as exc_info:
            await submit_for_review(client, "http://content-service", term, candidate)

    assert exc_info.value.status_code == 422
