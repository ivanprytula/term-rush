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
import time

from aiokafka import AIOKafkaConsumer

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository

logger = logging.getLogger(__name__)

TOPIC = "terms.published"
RESTART_BACKOFF_SECONDS = 5.0


class ConsumerHealth:
    """Tracks whether the background consumer loop is alive, for /ready.

    A dead consumer degrades cache freshness (falls back to the 300s TTL,
    see GrpcTermRepository) but never a hard outage — never gates liveness.
    """

    def __init__(self) -> None:
        self.last_alive_at: float = time.monotonic()

    def mark_alive(self) -> None:
        self.last_alive_at = time.monotonic()

    def is_stale(self, max_age_seconds: float = 60.0) -> bool:
        """True once the loop hasn't confirmed itself alive recently enough
        that a restart has plausibly failed repeatedly, not just backed off
        once."""
        return time.monotonic() - self.last_alive_at > max_age_seconds


async def consume_term_published(
    consumer: AIOKafkaConsumer,
    term_repository: GrpcTermRepository,
    health: ConsumerHealth | None = None,
) -> None:
    """Evict each published term_id from the cache until cancelled."""
    async for message in consumer:
        if health is not None:
            health.mark_alive()
        try:
            envelope = json.loads(message.value)
            term_id = envelope["payload"]["term_id"]
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Malformed TermPublished message, skipping: %s", exc)
            continue
        term_repository.invalidate(term_id)
        logger.info("Invalidated cached term %s", term_id)


async def _supervise(
    consumer: AIOKafkaConsumer,
    term_repository: GrpcTermRepository,
    health: ConsumerHealth,
) -> None:
    """Restart consume_term_published if it raises, until cancelled.

    aiokafka retries its own connection/broker errors internally without
    raising — this guards the remaining case: something unexpected (a bug,
    an unhandled error type) kills the loop outright. Without a supervisor
    that failure is permanent and silent: TermPublished stops being
    consumed for the rest of the process's life, degrading silently to the
    TTL-only fallback with nothing surfacing it.
    """
    while True:
        health.mark_alive()
        try:
            await consume_term_published(consumer, term_repository, health)
            return  # consumer exhausted cleanly (shouldn't happen; not an error)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Term cache invalidator crashed, restarting in %.0fs",
                RESTART_BACKOFF_SECONDS,
            )
            await asyncio.sleep(RESTART_BACKOFF_SECONDS)


def start_consumer_task(
    consumer: AIOKafkaConsumer,
    term_repository: GrpcTermRepository,
    health: ConsumerHealth,
) -> asyncio.Task[None]:
    """Spawn the supervised consumer loop as a background task.

    Caller (lifespan) owns cancellation: cancel the task and await it
    wrapped in suppress(asyncio.CancelledError) on shutdown.
    """
    return asyncio.create_task(_supervise(consumer, term_repository, health))


async def stop_consumer_task(task: asyncio.Task[None]) -> None:
    """Cancel and await the background consumer task."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
