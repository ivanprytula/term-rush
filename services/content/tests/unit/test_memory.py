"""In-memory adapter tests."""

from __future__ import annotations

import pytest

from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryTermRepository


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
    repo = InMemoryTermRepository()

    assert await repo.by_id("missing") is None


@pytest.mark.asyncio
async def test_random_returns_none_when_empty() -> None:
    repo = InMemoryTermRepository()

    assert await repo.random() is None


@pytest.mark.asyncio
async def test_upsert_then_by_id_round_trips(term: Term) -> None:
    repo = InMemoryTermRepository()

    await repo.upsert(term)

    assert await repo.by_id(term.id) == term


@pytest.mark.asyncio
async def test_upsert_replaces_existing_id(term: Term) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)

    replaced = term.model_copy(update={"expansion": "Unit-of-Work Pattern"})
    await repo.upsert(replaced)

    assert await repo.by_id(term.id) == replaced


@pytest.mark.asyncio
async def test_random_returns_the_only_term(term: Term) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)

    assert await repo.random() == term


@pytest.mark.asyncio
async def test_random_scopes_to_category(term: Term) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)
    other = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    await repo.upsert(other)

    result = await repo.random(category="python-keywords")

    assert result == other


@pytest.mark.asyncio
async def test_random_returns_none_when_category_has_no_terms(term: Term) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)

    assert await repo.random(category="nonexistent-category") is None


@pytest.mark.asyncio
async def test_categories_lists_every_distinct_slug(term: Term) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)
    await repo.upsert(
        term.model_copy(
            update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
        )
    )

    assert await repo.categories() == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_categories_empty_when_bank_is_empty() -> None:
    repo = InMemoryTermRepository()

    assert await repo.categories() == ()


@pytest.mark.asyncio
async def test_random_scopes_to_min_difficulty(term: Term) -> None:
    repo = InMemoryTermRepository()
    easy = term.model_copy(update={"id": "easy", "difficulty": Difficulty.EASY})
    hard = term.model_copy(update={"id": "hard", "difficulty": Difficulty.HARD})
    await repo.upsert(easy)
    await repo.upsert(hard)

    result = await repo.random(min_difficulty=int(Difficulty.MODERATE))

    assert result == hard


@pytest.mark.asyncio
async def test_random_scopes_to_require_examples(term: Term) -> None:
    repo = InMemoryTermRepository()
    no_examples = term.model_copy(update={"id": "no-examples", "examples": ()})
    with_examples = term.model_copy(
        update={"id": "with-examples", "examples": ("An example.",)}
    )
    await repo.upsert(no_examples)
    await repo.upsert(with_examples)

    result = await repo.random(require_examples=True)

    assert result == with_examples


@pytest.mark.asyncio
async def test_random_scopes_to_min_definition_length(term: Term) -> None:
    repo = InMemoryTermRepository()
    short = term.model_copy(update={"id": "short", "definitions": ("Too short.",)})
    long_enough = term.model_copy(update={"id": "long", "definitions": ("x" * 40,)})
    await repo.upsert(short)
    await repo.upsert(long_enough)

    result = await repo.random(min_definition_length=40)

    assert result == long_enough


@pytest.mark.asyncio
async def test_random_returns_none_when_no_term_matches_the_filters(
    term: Term,
) -> None:
    repo = InMemoryTermRepository()
    await repo.upsert(term)  # MODERATE difficulty (default), no examples

    assert await repo.random(require_examples=True) is None
