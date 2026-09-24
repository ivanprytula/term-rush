"""Request and response schemas for the API.

Validation happens here; the use cases work with validated domain objects.
All bounds sourced from domain.constants for consistency.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel
from pydantic import Field

from content_service.domain import constants
from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term

# Optional: GET /terms/random works without one (whole bank), but supplying
# a category slug scopes the pick to that collection.
CategoryQuery = Annotated[
    str | None,
    Query(pattern=r"^[a-z][a-z0-9-]*$", max_length=constants.TERM_SLUG_MAX_LEN),
]


class TermResponse(BaseModel):
    """A term, in full — content-service's own surface, unlike game-service's
    answer-hiding prompt response.
    """

    id: str
    term: str
    expansion: str
    definitions: tuple[str, ...]
    aliases: tuple[str, ...]
    categories: tuple[str, ...]
    difficulty: int
    examples: tuple[str, ...]
    related: tuple[str, ...]
    prerequisites: tuple[str, ...]
    common_mistakes: tuple[str, ...]

    @staticmethod
    def from_term(term: Term) -> TermResponse:
        """Convert a Term to a response."""
        return TermResponse(
            id=term.id,
            term=term.term,
            expansion=term.expansion,
            definitions=term.definitions,
            aliases=term.aliases,
            categories=tuple(str(c) for c in term.categories),
            difficulty=int(term.difficulty),
            examples=term.examples,
            related=term.related,
            prerequisites=term.prerequisites,
            common_mistakes=term.common_mistakes,
        )


class TermCategoriesResponse(BaseModel):
    """Every category slug present in the term bank."""

    categories: tuple[str, ...]


class PublishTermRequest(BaseModel):
    """Authoring payload to create or replace a term."""

    id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=constants.TERM_ID_MAX_LEN
    )
    term: str = Field(
        min_length=constants.TERM_ID_MIN_LEN, max_length=constants.TERM_ID_MAX_LEN
    )
    expansion: str = Field(
        min_length=constants.TERM_ID_MIN_LEN,
        max_length=constants.TERM_DEFINITION_MAX_LEN,
    )
    definitions: tuple[str, ...] = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    categories: tuple[str, ...] = Field(min_length=1)
    difficulty: int = int(Difficulty.MODERATE)
    examples: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    prerequisites: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()

    def to_term(self) -> Term:
        """Convert the validated request into a domain Term."""
        return Term(
            id=self.id,
            term=self.term,
            expansion=self.expansion,
            definitions=self.definitions,
            aliases=self.aliases,
            categories=tuple(Category(slug=c) for c in self.categories),
            difficulty=Difficulty(self.difficulty),
            examples=self.examples,
            related=self.related,
            prerequisites=self.prerequisites,
            common_mistakes=self.common_mistakes,
        )


class SubmitReviewCandidateRequest(BaseModel):
    """A pipeline-enriched, validated candidate submitted for review.

    Reuses PublishTermRequest's term shape rather than duplicating it —
    a candidate's term fields are validated the same way a directly
    authored term's are.
    """

    term: PublishTermRequest
    source_type: str = Field(max_length=64)
    source_file: str = Field(max_length=512)
    confidence: str = Field(max_length=16)


class ReviewCandidateResponse(BaseModel):
    """A review candidate, in full."""

    id: int
    term: TermResponse
    source_type: str
    source_file: str
    confidence: str
    status: str

    @staticmethod
    def from_candidate(candidate: ReviewCandidate) -> ReviewCandidateResponse:
        assert candidate.id is not None  # always set once read back from a repository
        return ReviewCandidateResponse(
            id=candidate.id,
            term=TermResponse.from_term(candidate.term),
            source_type=candidate.source_type,
            source_file=candidate.source_file,
            confidence=candidate.confidence,
            status=candidate.status.value,
        )


class ReviewQueueListResponse(BaseModel):
    """A page of review candidates, filtered by status."""

    candidates: tuple[ReviewCandidateResponse, ...]


ReviewStatusQuery = Annotated[ReviewStatus, Query()]


class ReviewCandidateConflictResponse(BaseModel):
    """A 409: the candidate exists but isn't in the state the requested
    transition requires. Carries the actual current status as a typed
    field, not just prose, so a client can branch on it (e.g. show
    "already approved" vs "already rejected") without parsing `error`.
    """

    error: str
    status_code: int = 409
    candidate_id: int
    current_status: ReviewStatus
    required_status: ReviewStatus = ReviewStatus.PENDING


class ErrorResponse(BaseModel):
    """Error response body.

    error: human-readable message (generic, no info leaks).
    status_code: HTTP status code (404 for term not found, 422 for
    validation, 500 for server errors).
    """

    error: str
    status_code: int = Field(ge=400, le=599, description="HTTP status code (400-599)")
