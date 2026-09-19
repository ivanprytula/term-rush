"""FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from anthropic import AsyncAnthropic

from api.config import settings
from application.ports import UnitOfWork
from domain.graders import AnswerEvaluator
from domain.graders import build_deterministic_evaluator
from domain.llm_grader import LLMRubricGrader
from infrastructure.database import create_db_engine
from infrastructure.llm_judge import AnthropicJudgePort
from infrastructure.memory import InMemoryUnitOfWork
from infrastructure.profanity_checker import BetterProfanityChecker
from infrastructure.sql_uow import SQLUnitOfWork

# Session factory and engine (created at app startup via lifespan)
_session_factory: Any = None
_engine: Any = None

# None when ANTHROPIC_API_KEY is unset: get_llm_grader then returns None and
# SubmitAnswer runs deterministic-only, same as Phase 1.
_llm_grader: LLMRubricGrader | None = (
    LLMRubricGrader(
        AnthropicJudgePort(AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY))
    )
    if settings.ANTHROPIC_API_KEY
    else None
)

# ENABLE_PROFANITY_CHECK toggles ProfanityGrader in the deterministic chain
# (domain/graders.py stays framework-free; the checker is constructed here).
_answer_evaluator = build_deterministic_evaluator(
    BetterProfanityChecker() if settings.ENABLE_PROFANITY_CHECK else None
)


async def _init_session_factory() -> None:
    """Initialize the session factory and engine (called from lifespan).

    No-ops when DATABASE_URL is unset: get_unit_of_work then falls back to
    the in-memory adapters, which is how tests run without a real database.
    """
    global _session_factory, _engine
    if settings.DATABASE_URL is None:
        return
    _engine, _session_factory = await create_db_engine(str(settings.DATABASE_URL))


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    """Provide a Unit of Work for the request (in-memory for tests, SQL for production).

    Manages session lifecycle: creates on entry, closes on exit.
    """
    if _session_factory is None:
        uow = InMemoryUnitOfWork()
        yield uow
    else:
        async with _session_factory() as session:
            yield SQLUnitOfWork(session)


def get_llm_grader() -> LLMRubricGrader | None:
    """Provide the LLM rubric grader, or None if ANTHROPIC_API_KEY is unset."""
    return _llm_grader


def get_answer_evaluator() -> AnswerEvaluator:
    """Provide the deterministic chain, profanity check included."""
    return _answer_evaluator
