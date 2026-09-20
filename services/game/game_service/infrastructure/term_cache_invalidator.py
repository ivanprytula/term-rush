"""Consumes TermPublished off Kafka and evicts the matching GrpcTermRepository entry.

Runs as a background task inside the API process (started/stopped via
lifespan), not a separate process: it must share the same
GrpcTermRepository instance request handlers read from, or invalidating a
cache nothing ever populated is a no-op. See ADR-0011.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from aiokafka import AIOKafkaConsumer

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository

logger = logging.getLogger(__name__)

TOPIC = "terms.published"


async def consume_term_published(
    consumer: AIOKafkaConsumer, term_repository: GrpcTermRepository
) -> None:
    """Evict each published term_id from the cache until cancelled."""
    async for message in consumer:
        try:
            envelope = json.loads(message.value)
            term_id = envelope["payload"]["term_id"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Malformed TermPublished message, skipping: %s", exc)
            continue
        term_repository.invalidate(term_id)
        logger.info("Invalidated cached term %s", term_id)


def start_consumer_task(
    consumer: AIOKafkaConsumer, term_repository: GrpcTermRepository
) -> asyncio.Task[None]:
    """Spawn consume_term_published as a background task.

    Caller (lifespan) owns cancellation: cancel the task and await it
    wrapped in suppress(asyncio.CancelledError) on shutdown.
    """
    return asyncio.create_task(consume_term_published(consumer, term_repository))


async def stop_consumer_task(task: asyncio.Task[None]) -> None:
    """Cancel and await the background consumer task."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
