"""TermCacheInvalidator tests: message parsing, cache eviction, malformed input."""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository
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
