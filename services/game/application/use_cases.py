"""Application use cases.

Pure business logic over ports; independent of Framework/Infrastructure.
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from hashlib import sha256

from application.ports import UnitOfWork
from domain.graders import AnswerEvaluator
from domain.graders import build_deterministic_evaluator
from domain.outcome import GradeOutcome
from domain.session import Session
from domain.session import SubmittedAnswer


class SubmitAnswer:
    """Grade an answer against a term."""

    def __init__(
        self,
        uow: UnitOfWork,
        evaluator: AnswerEvaluator | None = None,
    ) -> None:
        self.uow = uow
        self.evaluator = evaluator or build_deterministic_evaluator()

    async def execute(self, session_id: str, term_id: str, answer: str) -> GradeOutcome:
        """Grade the answer and record it against the session. Return cached
        outcome if available.

        Events (for Phase 2/3): AnswerGraded published on commit.
        """
        answer_hash = sha256(answer.encode()).hexdigest()

        async with self.uow:
            session = await self.uow.sessions.by_id(session_id)
            if session is None:
                session = Session(id=session_id, created_at=datetime.now(UTC))

            # Try cache first
            cached = await self.uow.grade_cache.get(term_id, answer_hash)
            if cached is not None:
                outcome = cached
            else:
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

            session = session.record(
                SubmittedAnswer(
                    term_id=term_id,
                    verdict=outcome.verdict,
                    score=outcome.score,
                    matched_via=outcome.matched_via,
                    submitted_at=datetime.now(UTC),
                )
            )
            await self.uow.sessions.save(session)

            # Commit happens in uow.__aexit__ on clean exit
            return outcome


class GetSession:
    """Fetch a session's recorded answers."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, session_id: str) -> Session:
        """Return the session. Raises ValueError if it does not exist."""
        async with self.uow:
            session = await self.uow.sessions.by_id(session_id)
            if session is None:
                raise ValueError(f"Session {session_id} not found")
            return session
