"""SQLRoundRepository against a real Postgres: exercises the total_score
column and index no in-memory test can validate."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from datetime import UTC
from datetime import datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import SubmittedAnswer
from game_service.infrastructure.database import Base
from game_service.infrastructure.sql_repositories import SQLRoundRepository

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


def _round(round_id: str, score: int) -> GameRound:
    return GameRound(
        id=round_id,
        created_at=datetime.now(UTC),
        answers=(
            SubmittedAnswer(
                term_id="uow",
                verdict=Verdict.CORRECT,
                score=score,
                matched_via=MatchedVia.EXACT,
                submitted_at=datetime.now(UTC),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_save_persists_total_score(session: AsyncSession) -> None:
    repo = SQLRoundRepository(session)
    await repo.save(_round("r1", score=42))
    await session.commit()

    round_ = await repo.by_id("r1")

    assert round_ is not None
    assert round_.total_score == 42


@pytest.mark.asyncio
async def test_top_by_score_orders_descending(session: AsyncSession) -> None:
    repo = SQLRoundRepository(session)
    for round_id, score in [("low", 10), ("high", 90), ("mid", 50)]:
        await repo.save(_round(round_id, score))
    await session.commit()

    top = await repo.top_by_score(limit=2)

    assert [r.id for r in top] == ["high", "mid"]


@pytest.mark.asyncio
async def test_top_by_score_respects_limit(session: AsyncSession) -> None:
    repo = SQLRoundRepository(session)
    for i in range(5):
        await repo.save(_round(f"r{i}", score=i))
    await session.commit()

    top = await repo.top_by_score(limit=3)

    assert len(top) == 3


@pytest.mark.asyncio
async def test_save_upsert_updates_total_score(session: AsyncSession) -> None:
    repo = SQLRoundRepository(session)
    await repo.save(_round("r1", score=10))
    await session.commit()

    updated = _round("r1", score=10).record(
        SubmittedAnswer(
            term_id="cqrs",
            verdict=Verdict.CORRECT,
            score=20,
            matched_via=MatchedVia.EXACT,
            submitted_at=datetime.now(UTC),
        ),
        datetime.now(UTC),
    )
    await repo.save(updated)
    await session.commit()

    round_ = await repo.by_id("r1")

    assert round_ is not None
    assert round_.total_score == 30
