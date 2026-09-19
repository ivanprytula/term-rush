"""Grading outcomes.

Typed results, never bools: the caller must be able to tell *why* an answer
scored what it did without catching exceptions or inspecting strings. The rubric
breakdown is what turns this from a quiz into a learning tool.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel
from pydantic import Field

from . import constants


class Verdict(StrEnum):
    CORRECT = "correct"
    PARTIAL = "partial"
    INCORRECT = "incorrect"


class MatchedVia(StrEnum):
    """Which grader in the chain produced the outcome.

    Surfaced to the player ("matched an alias") and to analytics, where the
    distribution tells us whether the LLM judge is earning its cost.
    """

    EXACT = "exact"
    ALIAS = "alias"
    FUZZY = "fuzzy"
    LLM_RUBRIC = "llm_rubric"
    FLAGGED = "flagged"


class RubricBreakdown(BaseModel):
    """The four-part learning rubric (weights: 40-30-20-10, heaviest first).

    Concept: do you know what it is? (40 pts)
    Expansion: do you know what the letters stand for? (30 pts)
    Purpose: do you know what it is for? (20 pts)
    Example: can you ground it in something concrete? (10 pts)

    Deterministic graders can only award Expansion. LLM judge in Phase 2 fills
    the rest. A player saying "Unit of Work" scores 30; one explaining the
    pattern scores 90. The inversion is the product thesis.
    Weights are sourced from constants.py so changes propagate everywhere.
    """

    model_config = {"frozen": True}

    concept: int = Field(ge=0, le=constants.CONCEPT_WEIGHT)
    expansion: int = Field(ge=0, le=constants.EXPANSION_WEIGHT)
    purpose: int = Field(ge=0, le=constants.PURPOSE_WEIGHT)
    example: int = Field(ge=0, le=constants.EXAMPLE_WEIGHT)

    @property
    def total(self) -> int:
        return self.concept + self.expansion + self.purpose + self.example

    @classmethod
    def expansion_only(cls) -> RubricBreakdown:
        """What a deterministic grader can award: it can confirm the expansion,
        but it cannot judge whether the player understood the concept. Phase 1
        graders use this; the Phase 2 LLM judge fills in the rest.
        """
        return cls(
            concept=0, expansion=constants.EXPANSION_WEIGHT, purpose=0, example=0
        )

    @classmethod
    def zero(cls) -> RubricBreakdown:
        return cls(concept=0, expansion=0, purpose=0, example=0)


class GradeOutcome(BaseModel):
    """The result of grading one answer against one term."""

    model_config = {"frozen": True}

    verdict: Verdict
    rubric: RubricBreakdown
    matched_via: MatchedVia
    confidence: float = Field(ge=0.0, le=1.0)
    feedback: str

    @property
    def score(self) -> int:
        return self.rubric.total

    @property
    def is_accepted(self) -> bool:
        """Whether this counts as a success for streak and SRS purposes.

        PARTIAL counts: the learning engine would rather reschedule a shaky term
        sooner than punish a player who understood most of it.
        """
        return self.verdict in (Verdict.CORRECT, Verdict.PARTIAL)


class StreamEventKind(StrEnum):
    """What kind of event a streamed grading response emits."""

    RATIONALE_DELTA = "rationale_delta"
    GRADED = "graded"


class StreamEvent(BaseModel):
    """One frame of a streamed grading response.

    RATIONALE_DELTA carries a chunk of live LLM feedback text (`text` set,
    `outcome` None) — zero or more of these, only when escalating to the LLM
    judge. GRADED carries the final GradeOutcome (`outcome` set, `text`
    None) — always exactly one, last. A verdict that never escalates (no
    opt-in, not PARTIAL, cache hit) emits only the single GRADED frame.
    """

    model_config = {"frozen": True}

    kind: StreamEventKind
    text: str | None = None
    outcome: GradeOutcome | None = None

    @classmethod
    def rationale_delta(cls, text: str) -> StreamEvent:
        return cls(kind=StreamEventKind.RATIONALE_DELTA, text=text)

    @classmethod
    def graded(cls, outcome: GradeOutcome) -> StreamEvent:
        return cls(kind=StreamEventKind.GRADED, outcome=outcome)
