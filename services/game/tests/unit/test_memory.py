"""In-memory adapter tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest

from game_service.domain.round import GameRound
from game_service.domain.term import Category
from game_service.domain.term import Term
from game_service.infrastructure.memory import InMemoryRoundRepository
from game_service.infrastructure.memory import InMemoryTermRepository


@pytest.fixture
def round_() -> GameRound:
    return GameRound(id="s1", created_at=datetime.now(UTC))


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )


@pytest.mark.asyncio
async def test_by_id_returns_none_when_absent() -> None:
    repo = InMemoryRoundRepository()

    assert await repo.by_id("missing") is None


@pytest.mark.asyncio
async def test_save_then_by_id_round_trips(round_: GameRound) -> None:
    repo = InMemoryRoundRepository()

    await repo.save(round_)

    assert await repo.by_id(round_.id) == round_


@pytest.mark.asyncio
async def test_random_returns_none_when_empty() -> None:
    repo = InMemoryTermRepository()

    assert await repo.random() is None


@pytest.mark.asyncio
async def test_random_scopes_to_category(term: Term) -> None:
    other = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    repo = InMemoryTermRepository({term.id: term, other.id: other})

    result = await repo.random(category="python-keywords")

    assert result == other


@pytest.mark.asyncio
async def test_random_returns_none_when_category_has_no_terms(term: Term) -> None:
    repo = InMemoryTermRepository({term.id: term})

    assert await repo.random(category="nonexistent-category") is None


@pytest.mark.asyncio
async def test_random_falls_back_within_category_once_excluded(term: Term) -> None:
    repo = InMemoryTermRepository({term.id: term})

    result = await repo.random(frozenset({term.id}), category="architecture")

    assert result == term


@pytest.mark.asyncio
async def test_categories_lists_every_distinct_slug(term: Term) -> None:
    other = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    repo = InMemoryTermRepository({term.id: term, other.id: other})

    assert await repo.categories() == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_categories_empty_when_bank_is_empty() -> None:
    repo = InMemoryTermRepository()

    assert await repo.categories() == ()
