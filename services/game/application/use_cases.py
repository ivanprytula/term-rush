"""Application use cases.

Pure business logic over ports; independent of Framework/Infrastructure.
"""

from __future__ import annotations

from hashlib import sha256

from application.ports import UnitOfWork
from domain.graders import AnswerEvaluator
from domain.graders import build_deterministic_evaluator
from domain.outcome import GradeOutcome


class SubmitAnswer:
    """Grade an answer against a term."""

    def __init__(
        self,
        uow: UnitOfWork,
        evaluator: AnswerEvaluator | None = None,
    ) -> None:
        self.uow = uow
        self.evaluator = evaluator or build_deterministic_evaluator()

    async def execute(self, term_id: str, answer: str) -> GradeOutcome:
        """Grade the answer. Return cached outcome if available.

        Events (for Phase 2/3): AnswerGraded published on commit.
        """
        answer_hash = sha256(answer.encode()).hexdigest()

        async with self.uow:
            # Try cache first
            cached = await self.uow.grade_cache.get(term_id, answer_hash)
            if cached is not None:
                return cached

            # Fetch term
            term = await self.uow.terms.by_id(term_id)
            if term is None:
                raise ValueError(f"Term {term_id} not found")

            # Grade
            outcome = self.evaluator.evaluate(answer, term)

            # Cache for future identical answers
            await self.uow.grade_cache.put(term_id, answer_hash, outcome)

            # Publish domain event (for Phase 2/3)
            await self.uow.events.publish(
                "AnswerGraded",
                {
                    "term_id": term_id,
                    "answer": answer,
                    "verdict": outcome.verdict.value,
                    "rubric": outcome.rubric.model_dump(),
                    "matched_via": outcome.matched_via.value,
                },
            )

            # Commit
            await self.uow.commit()

            return outcome
