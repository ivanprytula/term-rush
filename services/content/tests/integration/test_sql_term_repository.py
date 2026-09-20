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


def _term(term_id: str) -> Term:
    return Term(
        id=term_id,
        term=term_id.upper(),
        expansion=f"{term_id} expansion",
        definitions=(f"{term_id} definition.",),
        categories=(Category(slug="architecture"),),
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
