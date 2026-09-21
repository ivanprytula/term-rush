"""A play-through: the record of what a player attempted and how they scored.

Kept separate from Term (knowledge) and GradeOutcome (one grading result):
a GameRound is the append-only log that ties many outcomes to one player's run.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field

from game_service.domain import constants
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict


class RoundFull(Exception):
    """Raised when a round already holds ROUND_MAX_ANSWERS answers."""


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

    def record(self, answer: SubmittedAnswer) -> GameRound:
        """Return a new GameRound with the answer appended.

        Frozen like Term/GradeOutcome: callers replace, never mutate in place.

        Raises:
            RoundFull: the round already holds ROUND_MAX_ANSWERS answers.
        """
        if len(self.answers) >= constants.ROUND_MAX_ANSWERS:
            raise RoundFull(self.id)
        return self.model_copy(update={"answers": (*self.answers, answer)})
