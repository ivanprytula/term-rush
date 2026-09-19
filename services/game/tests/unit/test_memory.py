"""In-memory adapter tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest

from domain.session import Session
from infrastructure.memory import InMemorySessionRepository


@pytest.fixture
def session() -> Session:
    return Session(id="s1", created_at=datetime.now(UTC))


@pytest.mark.asyncio
async def test_by_id_returns_none_when_absent() -> None:
    repo = InMemorySessionRepository()

    assert await repo.by_id("missing") is None


@pytest.mark.asyncio
async def test_save_then_by_id_round_trips(session: Session) -> None:
    repo = InMemorySessionRepository()

    await repo.save(session)

    assert await repo.by_id(session.id) == session
