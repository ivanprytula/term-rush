"""SQLTermStatsRepository against a real Postgres: exercises the
upsert-increment no in-memory test can validate."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from game_service.domain.outcome import Verdict
from game_service.infrastructure.database import Base
from game_service.infrastructure.sql_repositories import SQLTermStatsRepository

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


@pytest.mark.asyncio
async def test_get_returns_none_before_any_record(session: AsyncSession) -> None:
    repo = SQLTermStatsRepository(session)

    assert await repo.get("uow") is None


@pytest.mark.asyncio
async def test_record_creates_and_tallies(session: AsyncSession) -> None:
    repo = SQLTermStatsRepository(session)
    await repo.record("uow", Verdict.CORRECT)
    await repo.record("uow", Verdict.PARTIAL)
    await repo.record("uow", Verdict.INCORRECT)
    await session.commit()

    stats = await repo.get("uow")

    assert stats is not None
    assert stats.correct_count == 1
    assert stats.partial_count == 1
    assert stats.incorrect_count == 1


@pytest.mark.asyncio
async def test_record_increments_on_conflict(session: AsyncSession) -> None:
    repo = SQLTermStatsRepository(session)
    for _ in range(3):
        await repo.record("uow", Verdict.CORRECT)
    await session.commit()

    stats = await repo.get("uow")

    assert stats is not None
    assert stats.correct_count == 3


@pytest.mark.asyncio
async def test_record_keeps_terms_independent(session: AsyncSession) -> None:
    repo = SQLTermStatsRepository(session)
    await repo.record("uow", Verdict.CORRECT)
    await repo.record("cqrs", Verdict.INCORRECT)
    await session.commit()

    uow_stats = await repo.get("uow")
    cqrs_stats = await repo.get("cqrs")

    assert uow_stats is not None
    assert uow_stats.correct_count == 1
    assert uow_stats.incorrect_count == 0
    assert cqrs_stats is not None
    assert cqrs_stats.incorrect_count == 1
