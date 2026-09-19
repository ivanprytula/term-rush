"""The LLM rubric judge.

Deliberately does not implement the (synchronous) Grader Protocol from
graders.py: an LLM call is I/O, so this is async. Wiring it into the
evaluation path — when to call it, how it composes with the sync
deterministic chain as fallback — is orchestration for the next slice, not
domain logic. This module only answers "what rubric would the LLM award".
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from pydantic import BaseModel
from pydantic import Field

from domain import constants
from domain.outcome import GradeOutcome
from domain.outcome import MatchedVia
from domain.outcome import RubricBreakdown
from domain.outcome import Verdict
from domain.term import Term

# A player who understood some of the concept but missed the rest shouldn't
# be marked wrong outright; below this they get INCORRECT.
PARTIAL_SCORE_THRESHOLD = 40
# Above this, the explanation is complete enough to count as CORRECT rather
# than PARTIAL.
CORRECT_SCORE_THRESHOLD = 70


class LLMJudgment(BaseModel):
    """A rubric opinion from the LLM judge, already parsed and schema-valid.

    The adapter (infrastructure/llm_judge.py, calling Anthropic directly —
    no task queue; see README's Phase 2 note on why Celery was scoped out)
    owns turning the model's raw text into this; the port boundary never
    carries untrusted raw JSON into the domain.
    """

    model_config = {"frozen": True}

    concept: int = Field(ge=0, le=constants.CONCEPT_WEIGHT)
    expansion: int = Field(ge=0, le=constants.EXPANSION_WEIGHT)
    purpose: int = Field(ge=0, le=constants.PURPOSE_WEIGHT)
    example: int = Field(ge=0, le=constants.EXAMPLE_WEIGHT)
    rationale: str


class LLMJudgePort(Protocol):
    """Grades one answer against one term using an LLM rubric judge.

    Implemented by an infrastructure adapter (AnthropicJudgePort, calling
    the Anthropic client directly). Declared here, not in
    application/ports.py, because it is a domain-level collaborator like
    Grader — application composes it, it does not own its contract.
    """

    async def judge(self, answer: str, term: Term) -> LLMJudgment:
        """Return a rubric judgment. Raises on provider failure or timeout —
        callers fall back to the deterministic chain rather than catching
        provider-specific exceptions here.
        """
        ...

    def stream_rationale(self, answer: str, term: Term) -> AsyncIterator[str]:
        """Stream a natural-language explanation of the answer, token by
        token, for live display while grading is in progress.

        Deliberately a separate call from judge(): tool_use forces
        structured output, so a tool-use call streams fragments of JSON
        ("{\"concept\": 3"), not readable prose. This call has no
        tool_choice, so what streams back is actual sentences. The
        structured rubric score still comes from judge() — callers that want
        both call this for the live text and judge() for the final score.
        """
        ...


class LLMRubricGrader:
    """Scores all four rubric slices via an LLM judge. Never abstains.

    Not a Grader (see module docstring) — invoked directly by whatever
    orchestrates the LLM path, not appended to AnswerEvaluator's chain.
    """

    def __init__(self, judge: LLMJudgePort) -> None:
        self._judge = judge

    async def grade(self, answer: str, term: Term) -> GradeOutcome:
        judgment = await self._judge.judge(answer, term)
        rubric = RubricBreakdown(
            concept=judgment.concept,
            expansion=judgment.expansion,
            purpose=judgment.purpose,
            example=judgment.example,
        )

        if rubric.total < PARTIAL_SCORE_THRESHOLD:
            verdict = Verdict.INCORRECT
        elif rubric.total < CORRECT_SCORE_THRESHOLD:
            verdict = Verdict.PARTIAL
        else:
            verdict = Verdict.CORRECT

        return GradeOutcome(
            verdict=verdict,
            rubric=rubric,
            matched_via=MatchedVia.LLM_RUBRIC,
            confidence=rubric.total / 100,
            feedback=judgment.rationale,
        )

    def stream_rationale(self, answer: str, term: Term) -> AsyncIterator[str]:
        """Passthrough to the port — see LLMJudgePort.stream_rationale.
        Callers combine this with grade() for the eventual structured score.
        """
        return self._judge.stream_rationale(answer, term)
