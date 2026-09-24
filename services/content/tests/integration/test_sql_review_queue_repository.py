"""SQLReviewQueueRepository against a real Postgres."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.database import Base
from content_service.infrastructure.sql_repositories import SQLReviewQueueRepository

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


def _candidate(term_id: str = "fsm") -> ReviewCandidate:
    return ReviewCandidate(
        term=Term(
            id=term_id,
            term=term_id.upper(),
            expansion=f"{term_id} expansion",
            definitions=(f"{term_id} definition.",),
            categories=(Category(slug="theory"),),
        ),
        source_type="dependency_manifest",
        source_file="pyproject.toml",
        confidence="high",
    )


@pytest.mark.asyncio
async def test_add_assigns_an_id_and_round_trips_the_term(
    session: AsyncSession,
) -> None:
    repo = SQLReviewQueueRepository(session)
    candidate = _candidate()

    added = await repo.add(candidate)
    await session.commit()

    assert added.id is not None
    fetched = await repo.by_id(added.id)
    assert fetched is not None
    assert fetched.term == candidate.term
    assert fetched.status == ReviewStatus.PENDING


@pytest.mark.asyncio
async def test_by_id_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SQLReviewQueueRepository(session)

    assert await repo.by_id(999) is None


@pytest.mark.asyncio
async def test_list_by_status_filters_correctly(session: AsyncSession) -> None:
    repo = SQLReviewQueueRepository(session)
    pending = await repo.add(_candidate("fsm"))
    approved = await repo.add(_candidate("uow"))
    await session.commit()
    assert approved.id is not None
    await repo.set_status(approved.id, ReviewStatus.APPROVED)
    await session.commit()

    pending_list = await repo.list_by_status(ReviewStatus.PENDING)
    approved_list = await repo.list_by_status(ReviewStatus.APPROVED)

    assert [c.id for c in pending_list] == [pending.id]
    assert [c.id for c in approved_list] == [approved.id]


@pytest.mark.asyncio
async def test_set_status_is_a_noop_when_missing(session: AsyncSession) -> None:
    repo = SQLReviewQueueRepository(session)

    await repo.set_status(999, ReviewStatus.APPROVED)  # must not raise
