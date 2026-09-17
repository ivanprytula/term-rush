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


class RubricBreakdown(BaseModel):
    """The four-part learning rubric (weights: 30-40-20-10).

    Expansion: do you know what the letters stand for? (30 pts)
    Concept: do you know what it is? (40 pts)
    Purpose: do you know what it is for? (20 pts)
    Example: can you ground it in something concrete? (10 pts)

    Deterministic graders can only award Expansion. LLM judge in Phase 2 fills
    the rest. A player saying "Unit of Work" scores 30; one explaining the
    pattern scores 90. The inversion is the product thesis.
    Weights are sourced from constants.py so changes propagate everywhere.
    """

    model_config = {"frozen": True}

    expansion: int = Field(ge=0, le=constants.EXPANSION_WEIGHT)
    concept: int = Field(ge=0, le=constants.CONCEPT_WEIGHT)
    purpose: int = Field(ge=0, le=constants.PURPOSE_WEIGHT)
    example: int = Field(ge=0, le=constants.EXAMPLE_WEIGHT)

    @property
    def total(self) -> int:
        return self.expansion + self.concept + self.purpose + self.example

    @classmethod
    def expansion_only(cls) -> RubricBreakdown:
        """What a deterministic grader can award: it can confirm the expansion,
        but it cannot judge whether the player understood the concept. Phase 1
        graders use this; the Phase 2 LLM judge fills in the rest.
        """
        return cls(
            expansion=constants.EXPANSION_WEIGHT, concept=0, purpose=0, example=0
        )

    @classmethod
    def zero(cls) -> RubricBreakdown:
        return cls(expansion=0, concept=0, purpose=0, example=0)


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
