"""In-memory adapter tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest

from game_service.domain.round import GameRound
from game_service.infrastructure.memory import InMemoryRoundRepository


@pytest.fixture
def round_() -> GameRound:
    return GameRound(id="s1", created_at=datetime.now(UTC))


@pytest.mark.asyncio
async def test_by_id_returns_none_when_absent() -> None:
    repo = InMemoryRoundRepository()

    assert await repo.by_id("missing") is None


@pytest.mark.asyncio
async def test_save_then_by_id_round_trips(round_: GameRound) -> None:
    repo = InMemoryRoundRepository()

    await repo.save(round_)

    assert await repo.by_id(round_.id) == round_
