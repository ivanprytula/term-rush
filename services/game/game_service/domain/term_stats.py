"""Observed difficulty: how players actually score against a term, not how
the term bank labels it.

Fed by AnswerGraded (ADR-0011) — the game's own play data recalibrating the
game, per the roadmap's mart_term_difficulty idea, without the warehouse.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from game_service.domain.outcome import Verdict


class TermStats(BaseModel):
    """Verdict tally for one term, accumulated across every graded answer."""

    model_config = {"frozen": True}

    term_id: str
    correct_count: int = Field(ge=0, default=0)
    partial_count: int = Field(ge=0, default=0)
    incorrect_count: int = Field(ge=0, default=0)

    @property
    def total_count(self) -> int:
        return self.correct_count + self.partial_count + self.incorrect_count

    @property
    def observed_difficulty(self) -> float | None:
        """Share of graded attempts that were not fully correct — 0.0 (easy
        in practice) to 1.0 (nobody gets it). None until a term has data."""
        if self.total_count == 0:
            return None
        return (self.partial_count + self.incorrect_count) / self.total_count

    def with_verdict(self, verdict: Verdict) -> TermStats:
        """Return a new TermStats with one more graded answer tallied."""
        counts = {
            "correct_count": self.correct_count,
            "partial_count": self.partial_count,
            "incorrect_count": self.incorrect_count,
        }
        counts[f"{verdict.value}_count"] += 1
        return TermStats(term_id=self.term_id, **counts)
