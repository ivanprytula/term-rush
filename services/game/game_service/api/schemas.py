"""Request and response schemas for the API.

Validation happens here; the use cases work with validated domain objects.
All bounds sourced from domain.constants for consistency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import Path
from fastapi import Query
from pydantic import BaseModel
from pydantic import Field

from game_service.domain import constants
from game_service.domain.outcome import GradeOutcome
from game_service.domain.outcome import StreamEvent
from game_service.domain.outcome import StreamEventKind
from game_service.domain.round import GameRound
from game_service.domain.round import RoundMode
from game_service.domain.term import Term
from game_service.domain.term_stats import TermStats

RoundIdPath = Annotated[str, Path(min_length=1, max_length=constants.ROUND_ID_MAX_LEN)]

# Optional: GET /terms/random works without a round (plain random term),
# but supplying one lets the use case exclude terms already seen this round.
RoundIdQuery = Annotated[
    str | None,
    Query(min_length=1, max_length=constants.ROUND_ID_MAX_LEN),
]

LeaderboardLimitQuery = Annotated[
    int,
    Query(ge=constants.LEADERBOARD_MIN_LIMIT, le=constants.LEADERBOARD_MAX_LIMIT),
]

TermIdPath = Annotated[
    str,
    Path(min_length=constants.TERM_ID_MIN_LEN, max_length=constants.TERM_ID_MAX_LEN),
]

# Optional: GET /terms/random works without one (whole bank), but supplying
# a category slug ("python-keywords", "abbreviations", ...) scopes the pick
# to that player-chosen collection.
CategoryQuery = Annotated[
    str | None,
    Query(pattern=r"^[a-z][a-z0-9-]*$", max_length=constants.TERM_SLUG_MAX_LEN),
]


class CreateRoundRequest(BaseModel):
    """Start a new round.

    mode: "classic" (untimed, default), "sprint" (fixed countdown),
    "survival" (3 lives), "boss" (one boss-eligible term), or "daily_20"
    (today's shared 20-term set).
    duration_seconds: Sprint-only; defaults to
    DEFAULT_SPRINT_DURATION_SECONDS if omitted. Ignored for every other mode.
    """

    mode: RoundMode = RoundMode.CLASSIC
    duration_seconds: int | None = Field(
        default=None,
        ge=constants.MIN_SPRINT_DURATION_SECONDS,
        le=constants.MAX_SPRINT_DURATION_SECONDS,
    )


class SubmitAnswerRequest(BaseModel):
    """Answer submission for grading.

    term_id: The term to grade against (1-64 chars).
    answer: The student's explanation (1-512 chars).
    use_llm_grading: opt into the LLM rubric judge for PARTIAL verdicts. No
    effect if the server has no LLM grader configured.
    """

    term_id: str = Field(
        min_length=constants.TERM_ID_MIN_LEN,
        max_length=constants.TERM_ID_MAX_LEN,
    )
    answer: str = Field(
        min_length=constants.ANSWER_MIN_LEN,
        max_length=constants.ANSWER_MAX_LEN,
    )
    use_llm_grading: bool = False


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


class RationaleDeltaEvent(BaseModel):
    """SSE 'rationale_delta' payload: one chunk of live LLM feedback text."""

    text: str


class SubmitAnswerStreamEvent(BaseModel):
    """One SSE frame from POST .../submit/stream, shaped for sse-starlette.

    event: "rationale_delta" (data: RationaleDeltaEvent) while the LLM judge
    is generating feedback, then exactly one "graded" (data:
    SubmitAnswerResponse) as the final frame. A verdict that never escalates
    emits only the single "graded" frame.
    """

    event: str
    data: str

    @staticmethod
    def from_stream_event(event: StreamEvent) -> SubmitAnswerStreamEvent:
        if event.kind is StreamEventKind.RATIONALE_DELTA:
            assert event.text is not None
            return SubmitAnswerStreamEvent(
                event=StreamEventKind.RATIONALE_DELTA.value,
                data=RationaleDeltaEvent(text=event.text).model_dump_json(),
            )
        assert event.outcome is not None
        return SubmitAnswerStreamEvent(
            event=StreamEventKind.GRADED.value,
            data=SubmitAnswerResponse.from_outcome(event.outcome).model_dump_json(),
        )


class SubmittedAnswerResponse(BaseModel):
    """One recorded answer in a round's history."""

    term_id: str
    verdict: str = Field(examples=["correct", "partial", "incorrect"])
    score: int = Field(ge=constants.MIN_SCORE, le=constants.MAX_SCORE)
    matched_via: str = Field(examples=["exact", "alias", "fuzzy", "llm_rubric"])
    submitted_at: datetime


class RoundResponse(BaseModel):
    """A round's recorded answer history."""

    id: str
    created_at: datetime
    answers: list[SubmittedAnswerResponse]
    mode: str = Field(examples=["classic", "sprint", "survival", "boss", "daily_20"])
    # Sprint only; null for every other mode. Lets the client render a
    # countdown without independently tracking wall-clock state.
    remaining_seconds: float | None = None
    # Whether the round has reached its mode's terminal state, whatever ends
    # it (Sprint's timer, Survival's lives, Boss's one answer, Daily 20's
    # term cap). Always false for Classic — it never ends server-side.
    is_over: bool = False
    # Survival only; null for every other mode.
    lives_remaining: int | None = None
    # Daily 20 only; null for every other mode.
    terms_remaining: int | None = None

    @staticmethod
    def from_round(round_: GameRound, now: datetime) -> RoundResponse:
        """Convert a GameRound to a response, as of `now`."""
        return RoundResponse(
            id=round_.id,
            created_at=round_.created_at,
            answers=[
                SubmittedAnswerResponse(
                    term_id=a.term_id,
                    verdict=a.verdict.value,
                    score=a.score,
                    matched_via=a.matched_via.value,
                    submitted_at=a.submitted_at,
                )
                for a in round_.answers
            ],
            mode=round_.mode.value,
            remaining_seconds=round_.remaining_seconds(now),
            is_over=round_.is_over(now),
            lives_remaining=round_.lives_remaining,
            terms_remaining=round_.terms_remaining,
        )


class LeaderboardEntryResponse(BaseModel):
    """One ranked round on the leaderboard."""

    round_id: str
    total_score: int
    created_at: datetime
    mode: str = Field(examples=["classic", "sprint", "survival", "boss", "daily_20"])

    @staticmethod
    def from_round(round_: GameRound) -> LeaderboardEntryResponse:
        """Convert a GameRound to a leaderboard entry."""
        return LeaderboardEntryResponse(
            round_id=round_.id,
            total_score=round_.total_score,
            created_at=round_.created_at,
            mode=round_.mode.value,
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


class TermCategoriesResponse(BaseModel):
    """Every collection a player can choose to play from."""

    categories: tuple[str, ...]


class TermStatsResponse(BaseModel):
    """Observed difficulty for one term (ADR-0011: the AnswerGraded
    consumer). observed_difficulty is null until the term has at least one
    graded answer — distinct from a 404, which means the term itself
    doesn't exist.
    """

    term_id: str
    correct_count: int
    partial_count: int
    incorrect_count: int
    observed_difficulty: float | None

    @staticmethod
    def from_stats(stats: TermStats) -> TermStatsResponse:
        """Convert a TermStats to a response."""
        return TermStatsResponse(
            term_id=stats.term_id,
            correct_count=stats.correct_count,
            partial_count=stats.partial_count,
            incorrect_count=stats.incorrect_count,
            observed_difficulty=stats.observed_difficulty,
        )

    @staticmethod
    def empty(term_id: str) -> TermStatsResponse:
        """No answer has been graded for this term yet."""
        return TermStatsResponse(
            term_id=term_id,
            correct_count=0,
            partial_count=0,
            incorrect_count=0,
            observed_difficulty=None,
        )


class ErrorResponse(BaseModel):
    """Error response body.

    error: human-readable message (generic, no info leaks).
    status_code: HTTP status code (422 for validation, 404 for term not found, 500 for server errors).
    """

    error: str
    status_code: int = Field(ge=400, le=599, description="HTTP status code (400–599)")
