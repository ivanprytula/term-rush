"""FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import grpc
from aiokafka import AIOKafkaConsumer
from aiokafka import AIOKafkaProducer
from anthropic import AsyncAnthropic

from game_service.api.config import settings
from game_service.application.ports import EventPublisher
from game_service.application.ports import TermStatsRepository
from game_service.application.ports import UnitOfWork
from game_service.domain.graders import AnswerEvaluator
from game_service.domain.graders import build_deterministic_evaluator
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.infrastructure.answer_graded_stats import TOPIC as ANSWER_TOPIC
from game_service.infrastructure.database import create_db_engine
from game_service.infrastructure.grpc_term_repository import GrpcTermRepository
from game_service.infrastructure.kafka_event_publisher import KafkaEventPublisher
from game_service.infrastructure.llm_judge import AnthropicJudgePort
from game_service.infrastructure.memory import InMemoryGradeCache
from game_service.infrastructure.memory import InMemoryTermStatsRepository
from game_service.infrastructure.memory import InMemoryUnitOfWork
from game_service.infrastructure.profanity_checker import BetterProfanityChecker
from game_service.infrastructure.sql_repositories import SQLTermStatsRepository
from game_service.infrastructure.sql_uow import SQLUnitOfWork
from game_service.infrastructure.term_cache_invalidator import TOPIC as TERM_TOPIC
from game_service.infrastructure.term_cache_invalidator import ConsumerHealth

# Session factory, engine, gRPC channel, and Kafka producer/consumers
# (created at app startup via lifespan). The consumers' supervisor tasks are
# spawned and joined by lifespan itself (a TaskGroup around its yield), not
# stored here — only the consumer objects and health trackers are shared
# with request handlers (get_consumer_health, /ready).
_session_factory: Any = None
_engine: Any = None
_grpc_channel: grpc.aio.Channel | None = None
_term_repository: GrpcTermRepository | None = None
_kafka_producer: AIOKafkaProducer | None = None
_event_publisher: EventPublisher | None = None
_kafka_consumer: AIOKafkaConsumer | None = None
_consumer_health: ConsumerHealth | None = None
_stats_consumer: AIOKafkaConsumer | None = None
_stats_consumer_health: ConsumerHealth | None = None

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

# One grade cache for the process's life, not per-request: a UnitOfWork is
# constructed fresh on every request, so a cache built inside it would never
# see a second lookup for the same term_id+answer. Shared here the same way
# _term_repository is shared, for both the SQL and in-memory (no DATABASE_URL)
# paths — the bug this corrects affected both.
_grade_cache = InMemoryGradeCache()

# Fallback for the no-DATABASE_URL path (tests): the same instance the
# in-memory answer_graded_stats consumer would write to. Never used when
# _session_factory is set — get_term_stats_repository opens a real session.
_in_memory_term_stats = InMemoryTermStatsRepository()


async def _init_session_factory() -> None:
    """Initialize the session factory, engine, gRPC channel, Kafka producer, and
    Kafka consumers (called from lifespan).

    No-ops when DATABASE_URL is unset: get_unit_of_work then falls back to
    the in-memory adapters, which is how tests run without a real database.
    KAFKA_BROKER_URL unset leaves _event_publisher None (SQLUnitOfWork falls
    back to its own in-memory no-op publisher) and starts no consumers.
    The term-cache consumer shares _term_repository with request handlers —
    invalidating a cache no request reads from would be a no-op (ADR-0011).

    Only starts each AIOKafkaConsumer and its ConsumerHealth; does not spawn
    a supervisor task. lifespan spawns both supervisors into its own
    TaskGroup once this returns, so the two tasks' lifetimes are scoped to
    that one `async with` block instead of tracked as separate globals.
    """
    global _session_factory, _engine, _grpc_channel, _term_repository
    global _kafka_producer, _event_publisher, _kafka_consumer
    global _consumer_health
    global _stats_consumer, _stats_consumer_health
    if settings.DATABASE_URL is None:
        return
    _engine, _session_factory = await create_db_engine(str(settings.DATABASE_URL))
    _grpc_channel = grpc.aio.insecure_channel(settings.CONTENT_SERVICE_GRPC_URL)
    _term_repository = GrpcTermRepository(_grpc_channel)
    if settings.KAFKA_BROKER_URL is not None:
        _kafka_producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BROKER_URL)
        await _kafka_producer.start()
        _event_publisher = KafkaEventPublisher(_kafka_producer)

        _kafka_consumer = AIOKafkaConsumer(
            TERM_TOPIC,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            group_id="game-service-term-cache-invalidator",
        )
        await _kafka_consumer.start()
        _consumer_health = ConsumerHealth()

        _stats_consumer = AIOKafkaConsumer(
            ANSWER_TOPIC,
            bootstrap_servers=settings.KAFKA_BROKER_URL,
            group_id="game-service-answer-graded-stats",
        )
        await _stats_consumer.start()
        _stats_consumer_health = ConsumerHealth()


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    """Provide a Unit of Work for the request (in-memory for tests, SQL for production).

    Manages session lifecycle: creates on entry, closes on exit. terms
    (GrpcTermRepository) and grade_cache are both shared instances whose
    lookups span requests, not reconstructed per call.
    """
    if _session_factory is None:
        uow = InMemoryUnitOfWork(grade_cache=_grade_cache)
        yield uow
    else:
        assert _term_repository is not None  # set alongside _session_factory
        async with _session_factory() as session:
            yield SQLUnitOfWork(
                session, _term_repository, _event_publisher, _grade_cache
            )


async def get_term_stats_repository() -> AsyncGenerator[TermStatsRepository]:
    """Provide a TermStatsRepository for the request (in-memory for tests,
    SQL for production) — read side of ADR-0011's AnswerGraded consumer.

    Not part of UnitOfWork: written by the Kafka consumer outside any
    request's transaction, read here as a plain query with no writes to
    commit.
    """
    if _session_factory is None:
        yield _in_memory_term_stats
    else:
        async with _session_factory() as session:
            yield SQLTermStatsRepository(session)


def get_llm_grader() -> LLMRubricGrader | None:
    """Provide the LLM rubric grader, or None if ANTHROPIC_API_KEY is unset."""
    return _llm_grader


def get_answer_evaluator() -> AnswerEvaluator:
    """Provide the deterministic chain, profanity check included."""
    return _answer_evaluator


def get_consumer_health() -> ConsumerHealth | None:
    """Provide the term-cache invalidator's health tracker, or None if Kafka
    is unconfigured."""
    return _consumer_health


def get_stats_consumer_health() -> ConsumerHealth | None:
    """Provide the answer-graded stats consumer's health tracker, or None if
    Kafka is unconfigured."""
    return _stats_consumer_health
