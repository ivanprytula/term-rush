"""A play-through: the record of what a player attempted and how they scored.

Kept separate from Term (knowledge) and GradeOutcome (one grading result):
a Session is the append-only log that ties many outcomes to one player's run.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel
from pydantic import Field

from domain import constants
from domain.outcome import MatchedVia
from domain.outcome import Verdict


class SessionFull(Exception):
    """Raised when a session already holds SESSION_MAX_ANSWERS answers."""


class SubmittedAnswer(BaseModel):
    """One graded answer, recorded against the session it was submitted in."""

    model_config = {"frozen": True}

    term_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=constants.TERM_ID_MAX_LEN
    )
    verdict: Verdict
    score: int = Field(ge=constants.MIN_SCORE, le=constants.MAX_SCORE)
    matched_via: MatchedVia
    submitted_at: datetime


class Session(BaseModel):
    """A player's play-through. Grows by appending SubmittedAnswer records."""

    model_config = {"frozen": True}

    id: str = Field(max_length=constants.SESSION_ID_MAX_LEN)
    created_at: datetime
    answers: tuple[SubmittedAnswer, ...] = ()

    def record(self, answer: SubmittedAnswer) -> Session:
        """Return a new Session with the answer appended.

        Frozen like Term/GradeOutcome: callers replace, never mutate in place.

        Raises:
            SessionFull: the session already holds SESSION_MAX_ANSWERS answers.
        """
        if len(self.answers) >= constants.SESSION_MAX_ANSWERS:
            raise SessionFull(self.id)
        return self.model_copy(update={"answers": (*self.answers, answer)})
