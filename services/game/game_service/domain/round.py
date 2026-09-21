"""A play-through: the record of what a player attempted and how they scored.

Kept separate from Term (knowledge) and GradeOutcome (one grading result):
a GameRound is the append-only log that ties many outcomes to one player's run.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel
from pydantic import Field

from game_service.domain import constants
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict


class RoundMode(StrEnum):
    """Classic: untimed, capped only by ROUND_MAX_ANSWERS. Sprint: a fixed
    countdown: see GameRound.started_at/duration_seconds."""

    CLASSIC = "classic"
    SPRINT = "sprint"


class RoundFull(Exception):
    """Raised when a round already holds ROUND_MAX_ANSWERS answers."""


class RoundExpired(Exception):
    """Raised when a Sprint round's timer has run out."""


class SubmittedAnswer(BaseModel):
    """One graded answer, recorded against the round it was submitted in."""

    model_config = {"frozen": True}

    term_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=constants.TERM_ID_MAX_LEN
    )
    verdict: Verdict
    score: int = Field(ge=constants.MIN_SCORE, le=constants.MAX_SCORE)
    matched_via: MatchedVia
    submitted_at: datetime


class GameRound(BaseModel):
    """A player's play-through. Grows by appending SubmittedAnswer records."""

    model_config = {"frozen": True}

    id: str = Field(max_length=constants.ROUND_ID_MAX_LEN)
    created_at: datetime
    answers: tuple[SubmittedAnswer, ...] = ()
    mode: RoundMode = RoundMode.CLASSIC
    # Sprint only; both None for Classic. Remaining time is derived from
    # these on every read rather than stored, so GameRound stays frozen.
    started_at: datetime | None = None
    duration_seconds: int | None = Field(
        default=None,
        ge=constants.MIN_SPRINT_DURATION_SECONDS,
        le=constants.MAX_SPRINT_DURATION_SECONDS,
    )

    @staticmethod
    def start(
        now: datetime,
        mode: RoundMode = RoundMode.CLASSIC,
        duration_seconds: int | None = None,
    ) -> GameRound:
        """Begin a new round with a server-minted id.

        duration_seconds is ignored outside Sprint mode.
        """
        is_sprint = mode is RoundMode.SPRINT
        if is_sprint and duration_seconds is None:
            duration_seconds = constants.DEFAULT_SPRINT_DURATION_SECONDS
        return GameRound(
            id=uuid.uuid4().hex,
            created_at=now,
            mode=mode,
            started_at=now if is_sprint else None,
            duration_seconds=duration_seconds if is_sprint else None,
        )

    @property
    def total_score(self) -> int:
        """Sum of all recorded answers' scores. Denormalized as a column for
        leaderboard sorting — see SQLRoundRepository."""
        return sum(a.score for a in self.answers)

    def remaining_seconds(self, now: datetime) -> float | None:
        """Seconds left in a Sprint round's countdown, floored at 0. None
        outside Sprint mode."""
        if self.mode is not RoundMode.SPRINT:
            return None
        assert self.started_at is not None
        assert self.duration_seconds is not None
        deadline = self.started_at + timedelta(seconds=self.duration_seconds)
        return max(0.0, (deadline - now).total_seconds())

    def is_expired(self, now: datetime) -> bool:
        """Classic rounds never expire; Sprint rounds expire once their
        countdown reaches zero."""
        remaining = self.remaining_seconds(now)
        return remaining is not None and remaining <= 0

    def record(self, answer: SubmittedAnswer, now: datetime) -> GameRound:
        """Return a new GameRound with the answer appended.

        Frozen like Term/GradeOutcome: callers replace, never mutate in place.

        Raises:
            RoundFull: the round already holds ROUND_MAX_ANSWERS answers.
            RoundExpired: a Sprint round's timer has run out.
        """
        if self.is_expired(now):
            raise RoundExpired(self.id)
        if len(self.answers) >= constants.ROUND_MAX_ANSWERS:
            raise RoundFull(self.id)
        return self.model_copy(update={"answers": (*self.answers, answer)})
