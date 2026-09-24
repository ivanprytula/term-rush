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


class ReviewCandidateNotPending(Exception):
    """Raised when approving or rejecting a candidate that isn't PENDING —
    a conflict with the queue's current state, not a missing resource.
    """

    def __init__(self, candidate_id: int, status: ReviewStatus) -> None:
        self.candidate_id = candidate_id
        self.status = status
        super().__init__(
            f"Review candidate {candidate_id} is not pending (status: {status.value})"
        )


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
