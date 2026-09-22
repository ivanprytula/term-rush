"""SQLTermRepository against a real Postgres: exercises the SQL random()
excludes/falls-back logic no in-memory test can validate."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term
from content_service.infrastructure.database import Base
from content_service.infrastructure.sql_repositories import SQLTermRepository

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def postgres_url() -> Generator[str]:
    with PostgresContainer("postgres:17-alpine") as container:
        yield container.get_connection_url().replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )


@pytest.fixture
async def session(postgres_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: Any = sessionmaker(  # type: ignore
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _term(
    term_id: str,
    *categories: str,
    difficulty: Difficulty = Difficulty.MODERATE,
    examples: tuple[str, ...] = (),
    definition: str = "",
) -> Term:
    return Term(
        id=term_id,
        term=term_id.upper(),
        expansion=f"{term_id} expansion",
        definitions=(definition or f"{term_id} definition.",),
        categories=tuple(Category(slug=c) for c in categories)
        or (Category(slug="architecture"),),
        difficulty=difficulty,
        examples=examples,
    )


@pytest.mark.asyncio
async def test_random_excludes_the_given_ids(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    for term_id in ("uow", "cqrs"):
        await repo.upsert(_term(term_id))
    await session.commit()

    result = await repo.random(frozenset({"uow"}))

    assert result is not None
    assert result.id == "cqrs"


@pytest.mark.asyncio
async def test_random_falls_back_once_all_ids_excluded(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("uow"))
    await session.commit()

    result = await repo.random(frozenset({"uow"}))

    assert result is not None
    assert result.id == "uow"


@pytest.mark.asyncio
async def test_random_returns_none_when_bank_is_empty(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)

    assert await repo.random() is None


@pytest.mark.asyncio
async def test_random_scopes_to_category(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("uow", "architecture"))
    await repo.upsert(_term("lambda", "python-keywords"))
    await session.commit()

    result = await repo.random(category="python-keywords")

    assert result is not None
    assert result.id == "lambda"


@pytest.mark.asyncio
async def test_random_returns_none_when_category_has_no_terms(
    session: AsyncSession,
) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("uow", "architecture"))
    await session.commit()

    assert await repo.random(category="nonexistent-category") is None


@pytest.mark.asyncio
async def test_random_falls_back_within_category_once_excluded(
    session: AsyncSession,
) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("lambda", "python-keywords"))
    await repo.upsert(_term("uow", "architecture"))
    await session.commit()

    result = await repo.random(frozenset({"lambda"}), category="python-keywords")

    assert result is not None
    assert result.id == "lambda"  # falls back within category, not to "uow"


@pytest.mark.asyncio
async def test_categories_lists_every_distinct_slug(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("uow", "architecture"))
    await repo.upsert(_term("lambda", "python-keywords"))
    await repo.upsert(_term("cqrs", "architecture"))
    await session.commit()

    result = await repo.categories()

    assert result == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_categories_empty_when_bank_is_empty(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)

    assert await repo.categories() == ()


@pytest.mark.asyncio
async def test_random_scopes_to_min_difficulty(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("easy", difficulty=Difficulty.EASY))
    await repo.upsert(_term("hard", difficulty=Difficulty.HARD))
    await session.commit()

    result = await repo.random(min_difficulty=int(Difficulty.MODERATE))

    assert result is not None
    assert result.id == "hard"


@pytest.mark.asyncio
async def test_random_scopes_to_require_examples(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("no-examples", examples=()))
    await repo.upsert(_term("with-examples", examples=("An example.",)))
    await session.commit()

    result = await repo.random(require_examples=True)

    assert result is not None
    assert result.id == "with-examples"


@pytest.mark.asyncio
async def test_random_scopes_to_min_definition_length(session: AsyncSession) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("short", definition="Too short."))
    await repo.upsert(_term("long", definition="x" * 40))
    await session.commit()

    result = await repo.random(min_definition_length=40)

    assert result is not None
    assert result.id == "long"


@pytest.mark.asyncio
async def test_random_returns_none_when_no_term_matches_the_filters(
    session: AsyncSession,
) -> None:
    repo = SQLTermRepository(session)
    await repo.upsert(_term("uow"))  # MODERATE difficulty, no examples
    await session.commit()

    assert await repo.random(require_examples=True) is None


@pytest.mark.asyncio
async def test_random_falls_back_within_filters_once_excluded(
    session: AsyncSession,
) -> None:
    """The excluded_ids fallback recursion must forward every filter — an
    exhausted Boss round should never fall back to an ineligible term."""
    repo = SQLTermRepository(session)
    await repo.upsert(_term("eligible", difficulty=Difficulty.HARD))
    await repo.upsert(_term("ineligible", difficulty=Difficulty.EASY))
    await session.commit()

    result = await repo.random(
        frozenset({"eligible"}), min_difficulty=int(Difficulty.MODERATE)
    )

    assert result is not None
    assert result.id == "eligible"  # falls back within the filter, not to "ineligible"
