"""TermCacheInvalidator tests: message parsing, cache eviction, malformed
input, supervisor restart, health tracking."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository
from game_service.infrastructure.term_cache_invalidator import ConsumerHealth
from game_service.infrastructure.term_cache_invalidator import _supervise
from game_service.infrastructure.term_cache_invalidator import consume_term_published


@dataclass
class _FakeMessage:
    value: bytes


class _FakeConsumer:
    """Replaces AIOKafkaConsumer: an async iterator over canned messages."""

    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._messages = messages

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for message in self._messages:
            yield message


def _envelope(term_id: str) -> bytes:
    return json.dumps(
        {"event_type": "TermPublished", "payload": {"term_id": term_id}}
    ).encode()


def _repository_with_cached_term(term_id: str) -> GrpcTermRepository:
    from game_service.domain.term import Category
    from game_service.domain.term import Difficulty
    from game_service.domain.term import Term

    repo = GrpcTermRepository.__new__(GrpcTermRepository)
    repo._cache = {
        term_id: (
            Term(
                id=term_id,
                term="UoW",
                expansion="Unit of Work",
                definitions=("A pattern.",),
                categories=(Category(slug="architecture"),),
                difficulty=Difficulty(3),
            ),
            0.0,
        )
    }
    return repo


@pytest.mark.asyncio
async def test_evicts_the_published_term_from_the_cache() -> None:
    repo = _repository_with_cached_term("uow")
    consumer = _FakeConsumer([_FakeMessage(_envelope("uow"))])

    await consume_term_published(consumer, repo)  # type: ignore

    assert "uow" not in repo._cache


@pytest.mark.asyncio
async def test_ignores_a_malformed_message_and_keeps_consuming() -> None:
    repo = _repository_with_cached_term("uow")
    consumer = _FakeConsumer(
        [_FakeMessage(b"not json"), _FakeMessage(_envelope("uow"))]
    )

    await consume_term_published(consumer, repo)  # type: ignore

    assert "uow" not in repo._cache


@pytest.mark.asyncio
async def test_ignores_a_message_missing_term_id() -> None:
    repo = _repository_with_cached_term("uow")
    consumer = _FakeConsumer([_FakeMessage(json.dumps({"payload": {}}).encode())])

    await consume_term_published(consumer, repo)  # type: ignore

    assert "uow" in repo._cache


def test_consumer_health_starts_alive() -> None:
    health = ConsumerHealth()

    assert not health.is_stale(max_age_seconds=60.0)


def test_consumer_health_is_stale_after_max_age() -> None:
    health = ConsumerHealth()
    health.last_alive_at -= 100.0

    assert health.is_stale(max_age_seconds=60.0)


def test_consumer_health_mark_alive_resets_staleness() -> None:
    health = ConsumerHealth()
    health.last_alive_at -= 100.0

    health.mark_alive()

    assert not health.is_stale(max_age_seconds=60.0)


class _RaisingThenEmptyConsumer:
    """Raises once (simulating an unhandled crash), then yields nothing."""

    def __init__(self) -> None:
        self.attempts = 0

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("simulated crash")
        return
        yield  # pragma: no cover - makes this an async generator


@pytest.mark.asyncio
async def test_supervise_restarts_after_a_crash() -> None:
    repo = _repository_with_cached_term("uow")
    consumer = _RaisingThenEmptyConsumer()
    health = ConsumerHealth()

    task = asyncio.create_task(_supervise(consumer, repo, health))  # type: ignore
    # _supervise sleeps RESTART_BACKOFF_SECONDS between attempts; give it
    # one event-loop turn to hit the crash and enter that sleep rather than
    # waiting out the real backoff.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert consumer.attempts == 1


@pytest.mark.asyncio
async def test_supervise_marks_health_alive_before_each_attempt() -> None:
    repo = _repository_with_cached_term("uow")
    consumer = _FakeConsumer([_FakeMessage(_envelope("uow"))])
    health = ConsumerHealth()
    health.last_alive_at -= 100.0

    await _supervise(consumer, repo, health)  # type: ignore

    assert not health.is_stale(max_age_seconds=60.0)
