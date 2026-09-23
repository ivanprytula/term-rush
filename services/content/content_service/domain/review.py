"""The review queue: LLM-authored candidates awaiting human approval.

"An agent writing to the live term bank unreviewed is a liability" —
ADR-0004. Every enriched candidate lands here first; approval is the only
path into the live terms table.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel
from pydantic import Field

from content_service.domain.term import Term


class ReviewStatus(StrEnum):
    """A candidate's position in the human approval workflow."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewCandidate(BaseModel):
    """One enriched, validated Term awaiting (or past) human review.

    `term` is a full knowledge object, not a bare name — enrich and
    validate have already run by the time a candidate reaches the queue.
    `id` is a queue-assigned identity, separate from `term.id`: the same
    term id can be resubmitted after a rejection.
    """

    id: int | None = None
    term: Term
    source_type: str = Field(max_length=64)
    source_file: str = Field(max_length=512)
    confidence: str = Field(max_length=16)
    status: ReviewStatus = ReviewStatus.PENDING
