"""Consumes AnswerGraded off Kafka and tallies verdicts into TermStatsRepository.

Runs as a background task inside the API process (started/stopped via
lifespan), mirroring term_cache_invalidator.py's shape. Unlike that
consumer, this one writes to Postgres, so it opens its own short-lived
session per message rather than sharing a request's session. See ADR-0011:
AnswerGraded's first consumer.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from typing import Any

from aiokafka import AIOKafkaConsumer

from game_service.application.ports import TermStatsRepository
from game_service.domain.outcome import Verdict
from game_service.infrastructure.sql_repositories import SQLTermStatsRepository
from game_service.infrastructure.term_cache_invalidator import ConsumerHealth

logger = logging.getLogger(__name__)

TOPIC = "answers.graded"
RESTART_BACKOFF_SECONDS = 5.0

# Constructs a repository from a session. Defaults to the real SQL adapter;
# tests pass a fake to exercise message-parsing/supervisor behavior without
# a database.
RepositoryFactory = Callable[[Any], TermStatsRepository]


async def consume_answer_graded(
    consumer: AIOKafkaConsumer,
    session_factory: Any,
    health: ConsumerHealth | None = None,
    repository_factory: RepositoryFactory = SQLTermStatsRepository,
) -> None:
    """Tally each graded answer's verdict against its term until cancelled.

    Opens a fresh session per message and commits it — this consumer runs
    outside any request's transaction, so it owns its own commit boundary.
    """
    async for message in consumer:
        if health is not None:
            health.mark_alive()
        try:
            envelope = json.loads(message.value)
            term_id = envelope["payload"]["term_id"]
            verdict = Verdict(envelope["payload"]["verdict"])
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("Malformed AnswerGraded message, skipping: %s", exc)
            continue
        async with session_factory() as session:
            await repository_factory(session).record(term_id, verdict)
            await session.commit()
        logger.info("Tallied %s verdict for term %s", verdict.value, term_id)


async def _supervise(
    consumer: AIOKafkaConsumer,
    session_factory: Any,
    health: ConsumerHealth,
    repository_factory: RepositoryFactory = SQLTermStatsRepository,
) -> None:
    """Restart consume_answer_graded if it raises, until cancelled.

    Same rationale as term_cache_invalidator._supervise: aiokafka retries
    its own broker errors internally; this guards against an unexpected bug
    killing the loop outright and silently ending stats collection for the
    rest of the process's life.
    """
    while True:
        health.mark_alive()
        try:
            await consume_answer_graded(
                consumer, session_factory, health, repository_factory
            )
            return  # consumer exhausted cleanly (shouldn't happen; not an error)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Answer-graded stats consumer crashed, restarting in %.0fs",
                RESTART_BACKOFF_SECONDS,
            )
            await asyncio.sleep(RESTART_BACKOFF_SECONDS)


def start_consumer_task(
    consumer: AIOKafkaConsumer,
    session_factory: Any,
    health: ConsumerHealth,
) -> asyncio.Task[None]:
    """Spawn the supervised consumer loop as a background task.

    Caller (lifespan) owns cancellation: cancel the task and await it
    wrapped in suppress(asyncio.CancelledError) on shutdown.
    """
    return asyncio.create_task(_supervise(consumer, session_factory, health))


async def stop_consumer_task(task: asyncio.Task[None]) -> None:
    """Cancel and await the background consumer task."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
