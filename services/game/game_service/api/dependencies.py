"""FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import grpc
from anthropic import AsyncAnthropic

from game_service.api.config import settings
from game_service.application.ports import UnitOfWork
from game_service.domain.graders import AnswerEvaluator
from game_service.domain.graders import build_deterministic_evaluator
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.infrastructure.database import create_db_engine
from game_service.infrastructure.grpc_term_repository import GrpcTermRepository
from game_service.infrastructure.llm_judge import AnthropicJudgePort
from game_service.infrastructure.memory import InMemoryUnitOfWork
from game_service.infrastructure.profanity_checker import BetterProfanityChecker
from game_service.infrastructure.sql_uow import SQLUnitOfWork

# Session factory, engine, and gRPC channel (created at app startup via lifespan)
_session_factory: Any = None
_engine: Any = None
_grpc_channel: grpc.aio.Channel | None = None
_term_repository: GrpcTermRepository | None = None

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
    """Initialize the session factory, engine, and gRPC channel (called from lifespan).

    No-ops when DATABASE_URL is unset: get_unit_of_work then falls back to
    the in-memory adapters, which is how tests run without a real database.
    """
    global _session_factory, _engine, _grpc_channel, _term_repository
    if settings.DATABASE_URL is None:
        return
    _engine, _session_factory = await create_db_engine(str(settings.DATABASE_URL))
    _grpc_channel = grpc.aio.insecure_channel(settings.CONTENT_SERVICE_GRPC_URL)
    _term_repository = GrpcTermRepository(_grpc_channel)


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    """Provide a Unit of Work for the request (in-memory for tests, SQL for production).

    Manages session lifecycle: creates on entry, closes on exit. terms is a
    shared GrpcTermRepository instance (its lookup cache spans requests).
    """
    if _session_factory is None:
        uow = InMemoryUnitOfWork()
        yield uow
    else:
        assert _term_repository is not None  # set alongside _session_factory
        async with _session_factory() as session:
            yield SQLUnitOfWork(session, _term_repository)


def get_llm_grader() -> LLMRubricGrader | None:
    """Provide the LLM rubric grader, or None if ANTHROPIC_API_KEY is unset."""
    return _llm_grader


def get_answer_evaluator() -> AnswerEvaluator:
    """Provide the deterministic chain, profanity check included."""
    return _answer_evaluator
