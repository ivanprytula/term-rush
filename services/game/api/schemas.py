"""Request and response schemas for the API.

Validation happens here; the use cases work with validated domain objects.
All bounds sourced from domain.constants for consistency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Path
from pydantic import BaseModel
from pydantic import Field

from domain import constants
from domain.outcome import GradeOutcome
from domain.session import Session
from domain.term import Term

SessionIdPath = Annotated[
    str, Path(min_length=1, max_length=constants.SESSION_ID_MAX_LEN)
]


class SubmitAnswerRequest(BaseModel):
    """Answer submission for grading.

    term_id: The term to grade against (1-64 chars).
    answer: The student's explanation (1-512 chars).
    """

    term_id: str = Field(
        min_length=constants.TERM_ID_MIN_LEN,
        max_length=constants.TERM_ID_MAX_LEN,
    )
    answer: str = Field(
        min_length=constants.ANSWER_MIN_LEN,
        max_length=constants.ANSWER_MAX_LEN,
    )


class RubricBreakdownResponse(BaseModel):
    """The four-part learning rubric in a response.

    Weights: concept 40, expansion 30, purpose 20, example 10 (total ≤100).
    Each component is 0 if the student answer missed that dimension.
    """

    concept: int = Field(ge=0, le=constants.CONCEPT_WEIGHT)
    expansion: int = Field(ge=0, le=constants.EXPANSION_WEIGHT)
    purpose: int = Field(ge=0, le=constants.PURPOSE_WEIGHT)
    example: int = Field(ge=0, le=constants.EXAMPLE_WEIGHT)
    total: int = Field(ge=constants.MIN_SCORE, le=constants.MAX_SCORE)


class SubmitAnswerResponse(BaseModel):
    """The result of grading one answer.

    verdict: one of correct, partial, incorrect.
    matched_via: grading path (exact match, alias, fuzzy match, or LLM rubric).
    confidence: 0.0–1.0, higher = more certain (exact=1.0, fuzzy~0.5, llm variable).
    feedback: localized explanation for the student.
    score: sum of rubric breakdown (0–100).
    """

    verdict: str = Field(
        examples=["correct", "partial", "incorrect"],
        description="Grading outcome",
    )
    score: int = Field(
        ge=constants.MIN_SCORE,
        le=constants.MAX_SCORE,
        description="Total score from rubric breakdown",
    )
    matched_via: str = Field(
        examples=["exact", "alias", "fuzzy", "llm_rubric"],
        description="Which grader matched the answer",
    )
    confidence: float = Field(
        ge=constants.MIN_CONFIDENCE,
        le=constants.MAX_CONFIDENCE,
        description="Certainty of the match (0.0–1.0)",
    )
    feedback: str = Field(description="Explanation for the student")
    rubric: RubricBreakdownResponse

    @staticmethod
    def from_outcome(outcome: GradeOutcome) -> SubmitAnswerResponse:
        """Convert a GradeOutcome to a response."""
        return SubmitAnswerResponse(
            verdict=outcome.verdict.value,
            score=outcome.score,
            matched_via=outcome.matched_via.value,
            confidence=outcome.confidence,
            feedback=outcome.feedback,
            rubric=RubricBreakdownResponse(
                concept=outcome.rubric.concept,
                expansion=outcome.rubric.expansion,
                purpose=outcome.rubric.purpose,
                example=outcome.rubric.example,
                total=outcome.rubric.total,
            ),
        )


class SubmittedAnswerResponse(BaseModel):
    """One recorded answer in a session's history."""

    term_id: str
    verdict: str = Field(examples=["correct", "partial", "incorrect"])
    score: int = Field(ge=constants.MIN_SCORE, le=constants.MAX_SCORE)
    matched_via: str = Field(examples=["exact", "alias", "fuzzy", "llm_rubric"])
    submitted_at: datetime


class SessionResponse(BaseModel):
    """A session's recorded answer history."""

    id: str
    created_at: datetime
    answers: list[SubmittedAnswerResponse]

    @staticmethod
    def from_session(session: Session) -> SessionResponse:
        """Convert a Session to a response."""
        return SessionResponse(
            id=session.id,
            created_at=session.created_at,
            answers=[
                SubmittedAnswerResponse(
                    term_id=a.term_id,
                    verdict=a.verdict.value,
                    score=a.score,
                    matched_via=a.matched_via.value,
                    submitted_at=a.submitted_at,
                )
                for a in session.answers
            ],
        )


class TermPromptResponse(BaseModel):
    """A term presented to the player. Excludes the expansion/definitions
    so the answer isn't leaked in the prompt.
    """

    id: str
    term: str

    @staticmethod
    def from_term(term: Term) -> TermPromptResponse:
        """Convert a Term to a prompt response."""
        return TermPromptResponse(id=term.id, term=term.term)


class ErrorResponse(BaseModel):
    """Error response body.

    error: human-readable message (generic, no info leaks).
    status_code: HTTP status code (422 for validation, 404 for term not found, 500 for server errors).
    """

    error: str
    status_code: int = Field(ge=400, le=599, description="HTTP status code (400–599)")
