"""Which terms to show next. Weakness-driven, not a memory model."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic import Field

from game_service.domain import constants
from game_service.domain.outcome import GradeOutcome

# A term is "weak" below this rubric score. 70 = knows the concept, not just
# the expansion (30) — see RubricBreakdown weights.
WEAK_SCORE_THRESHOLD = 70
RECENT_WINDOW = constants.RECENT_WINDOW_DAYS


class TermPerformance(BaseModel):
    """Rolling performance for one term, one player."""

    model_config = {"frozen": True}

    term_id: str
    attempts: int = Field(ge=0)
    recent_scores: tuple[int, ...] = ()

    @property
    def average_score(self) -> float:
        if not self.recent_scores:
            return 0.0
        return sum(self.recent_scores) / len(self.recent_scores)

    @property
    def is_weak(self) -> bool:
        return bool(self.recent_scores) and self.average_score < WEAK_SCORE_THRESHOLD

    def record(self, outcome: GradeOutcome) -> TermPerformance:
        scores = (*self.recent_scores, outcome.score)[-RECENT_WINDOW:]
        return TermPerformance(
            term_id=self.term_id,
            attempts=self.attempts + 1,
            recent_scores=scores,
        )


def priority(performance: TermPerformance) -> float:
    """Higher sorts first. Unseen terms outrank mastered ones."""
    if performance.attempts == 0:
        return 100.0
    return 100.0 - performance.average_score
