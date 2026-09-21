"""AnswerGradedStats consumer tests: message parsing, tallying, malformed
input, supervisor restart, health tracking. Uses a fake TermStatsRepository
(no real DB) — SQLTermStatsRepository itself is covered by
test_sql_term_stats_repository.py against a real Postgres."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import pytest

from game_service.application.ports import TermStatsRepository
from game_service.domain.outcome import Verdict
from game_service.domain.term_stats import TermStats
from game_service.infrastructure.answer_graded_stats import _supervise
from game_service.infrastructure.answer_graded_stats import consume_answer_graded
from game_service.infrastructure.term_cache_invalidator import ConsumerHealth


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


class _FakeRepository(TermStatsRepository):
    """Records (term_id, verdict) calls in place of SQLTermStatsRepository."""

    def __init__(self) -> None:
        self.recorded: list[tuple[str, Verdict]] = []

    async def get(self, term_id: str) -> TermStats | None:
        raise NotImplementedError

    async def record(self, term_id: str, verdict: Verdict) -> None:
        self.recorded.append((term_id, verdict))


class _FakeSession:
    """Replaces the `async with session_factory() as session` scope."""

    def __init__(self) -> None:
        self.committed = False

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


def _session_factory_for(repo: _FakeRepository, session: _FakeSession):
    def repository_factory(_session: object) -> _FakeRepository:
        return repo

    return (lambda: session), repository_factory


def _envelope(term_id: str, verdict: Verdict) -> bytes:
    return json.dumps(
        {
            "event_type": "AnswerGraded",
            "payload": {"term_id": term_id, "verdict": verdict.value},
        }
    ).encode()


@pytest.mark.asyncio
async def test_tallies_the_graded_verdict() -> None:
    repo = _FakeRepository()
    session = _FakeSession()
    session_factory, repository_factory = _session_factory_for(repo, session)
    consumer = _FakeConsumer([_FakeMessage(_envelope("uow", Verdict.CORRECT))])

    await consume_answer_graded(
        consumer,  # type: ignore
        session_factory,
        repository_factory=repository_factory,
    )

    assert repo.recorded == [("uow", Verdict.CORRECT)]
    assert session.committed


@pytest.mark.asyncio
async def test_ignores_a_malformed_message_and_keeps_consuming() -> None:
    repo = _FakeRepository()
    session = _FakeSession()
    session_factory, repository_factory = _session_factory_for(repo, session)
    consumer = _FakeConsumer(
        [_FakeMessage(b"not json"), _FakeMessage(_envelope("uow", Verdict.PARTIAL))]
    )

    await consume_answer_graded(
        consumer,  # type: ignore
        session_factory,
        repository_factory=repository_factory,
    )

    assert repo.recorded == [("uow", Verdict.PARTIAL)]


@pytest.mark.asyncio
async def test_ignores_a_message_missing_term_id() -> None:
    repo = _FakeRepository()
    session = _FakeSession()
    session_factory, repository_factory = _session_factory_for(repo, session)
    consumer = _FakeConsumer(
        [_FakeMessage(json.dumps({"payload": {"verdict": "correct"}}).encode())]
    )

    await consume_answer_graded(
        consumer,  # type: ignore
        session_factory,
        repository_factory=repository_factory,
    )

    assert repo.recorded == []


@pytest.mark.asyncio
async def test_ignores_a_message_with_an_unknown_verdict() -> None:
    repo = _FakeRepository()
    session = _FakeSession()
    session_factory, repository_factory = _session_factory_for(repo, session)
    consumer = _FakeConsumer(
        [
            _FakeMessage(
                json.dumps(
                    {"payload": {"term_id": "uow", "verdict": "not_a_verdict"}}
                ).encode()
            )
        ]
    )

    await consume_answer_graded(
        consumer,  # type: ignore
        session_factory,
        repository_factory=repository_factory,
    )

    assert repo.recorded == []


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


def _fake_repository_factory(_session: object) -> _FakeRepository:
    return _FakeRepository()


@pytest.mark.asyncio
async def test_supervise_restarts_after_a_crash() -> None:
    consumer = _RaisingThenEmptyConsumer()
    health = ConsumerHealth()

    task = asyncio.create_task(
        _supervise(
            consumer,  # type: ignore
            lambda: _FakeSession(),
            health,
            repository_factory=_fake_repository_factory,
        )
    )
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
    consumer = _FakeConsumer([_FakeMessage(_envelope("uow", Verdict.CORRECT))])
    health = ConsumerHealth()
    health.last_alive_at -= 100.0

    await asyncio.wait_for(
        _supervise(
            consumer,  # type: ignore
            lambda: _FakeSession(),
            health,
            repository_factory=_fake_repository_factory,
        ),
        timeout=5.0,
    )

    assert not health.is_stale(max_age_seconds=60.0)
