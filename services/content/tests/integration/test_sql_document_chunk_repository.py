"""SQLDocumentChunkRepository against a real Postgres."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from content_service.domain.document_chunk import DocumentChunk
from content_service.infrastructure.database import Base
from content_service.infrastructure.sql_repositories import SQLDocumentChunkRepository

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


def _chunk(source_file: str = "contract.pdf", chunk_index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        text=f"chunk {chunk_index} of {source_file}",
        source_file=source_file,
        chunk_index=chunk_index,
        char_start=chunk_index * 100,
        char_end=chunk_index * 100 + 50,
    )


@pytest.mark.asyncio
async def test_add_batch_assigns_ids_and_round_trips(session: AsyncSession) -> None:
    repo = SQLDocumentChunkRepository(session)
    chunks = (_chunk(chunk_index=0), _chunk(chunk_index=1))

    added = await repo.add_batch(chunks)
    await session.commit()

    assert all(c.id is not None for c in added)
    assert [c.id for c in added] == sorted(c.id for c in added)  # type: ignore


@pytest.mark.asyncio
async def test_by_source_file_returns_only_matching_chunks_in_order(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)
    await repo.add_batch(
        (
            _chunk("a.pdf", chunk_index=1),
            _chunk("a.pdf", chunk_index=0),
            _chunk("b.pdf", chunk_index=0),
        )
    )
    await session.commit()

    fetched = await repo.by_source_file("a.pdf")

    assert [c.chunk_index for c in fetched] == [0, 1]
    assert all(c.source_file == "a.pdf" for c in fetched)


@pytest.mark.asyncio
async def test_by_source_file_returns_empty_when_no_match(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)

    assert await repo.by_source_file("missing.pdf") == ()


@pytest.mark.asyncio
async def test_delete_by_source_file_removes_only_matching_chunks(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)
    await repo.add_batch((_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("b.pdf", 0)))
    await session.commit()

    await repo.delete_by_source_file("a.pdf")
    await session.commit()

    assert await repo.by_source_file("a.pdf") == ()
    assert len(await repo.by_source_file("b.pdf")) == 1


@pytest.mark.asyncio
async def test_delete_then_add_batch_reingests_without_conflict(
    session: AsyncSession,
) -> None:
    """The replace-semantics building block: delete_by_source_file
    followed by add_batch for the same (source_file, chunk_index) pairs
    doesn't hit the unique constraint - proves the fix for the rejection
    IngestDocumentChunks used to risk on a plain re-insert.
    """
    repo = SQLDocumentChunkRepository(session)
    await repo.add_batch((_chunk("a.pdf", 0), _chunk("a.pdf", 1)))
    await session.commit()

    await repo.delete_by_source_file("a.pdf")
    await repo.add_batch((_chunk("a.pdf", 0),))
    await session.commit()

    fetched = await repo.by_source_file("a.pdf")
    assert [c.chunk_index for c in fetched] == [0]
