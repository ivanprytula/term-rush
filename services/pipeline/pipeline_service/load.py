"""Load: submit a validated EnrichedTerm to content-service's review queue.

REST, not a shared DB connection — pipeline-service is a separate service
from content-service, and the architecture invariant against multiple
services touching one database applies the same way it does between
game-service and content-service (gRPC there, REST here — content-service
owns review_queue, pipeline-service is a caller like any other client).
"""

from __future__ import annotations

import httpx

from pipeline_service.candidate import TermCandidate
from pipeline_service.enriched_term import EnrichedTerm


class ReviewCandidateRejected(Exception):
    """content-service refused the submission (e.g. 422 on a malformed
    term) — distinct from a network/connectivity failure, which raises
    httpx's own exception types instead.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"content-service rejected candidate: {status_code} {body}")


def _submission_payload(term: EnrichedTerm, candidate: TermCandidate) -> dict:
    return {
        "term": {
            "id": term.id,
            "term": term.term,
            "expansion": term.expansion,
            "definitions": list(term.definitions),
            "aliases": list(term.aliases),
            "categories": list(term.categories),
            "difficulty": term.difficulty,
            "examples": list(term.examples),
            "related": list(term.related),
            "prerequisites": list(term.prerequisites),
            "common_mistakes": list(term.common_mistakes),
        },
        "source_type": candidate.source_type.value,
        "source_file": candidate.source_file,
        "confidence": candidate.confidence.value,
    }


async def submit_for_review(
    client: httpx.AsyncClient,
    content_service_url: str,
    term: EnrichedTerm,
    candidate: TermCandidate,
) -> int:
    """POST the enriched, validated term to content-service's review
    queue. Returns the assigned review-queue candidate id.

    Raises ReviewCandidateRejected on a 4xx; httpx's own exceptions
    (ConnectError, TimeoutException, ...) propagate for connectivity
    failures — the caller distinguishes "content-service said no" from
    "couldn't reach content-service".
    """
    response = await client.post(
        f"{content_service_url}/review-queue/candidates",
        json=_submission_payload(term, candidate),
    )
    if response.status_code >= 400:
        raise ReviewCandidateRejected(response.status_code, response.text)
    return int(response.json()["id"])
