"""SQLDocumentChunkRepository against a real Postgres."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from collections.abc import Generator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from content_service.domain import constants
from content_service.domain.document_chunk import DocumentChunk
from content_service.infrastructure.database import Base
from content_service.infrastructure.sql_repositories import SQLDocumentChunkRepository

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def postgres_url() -> Generator[str]:
    # pgvector image, not plain postgres: document_chunks.embedding (ADR-0012
    # Slice 2) needs `CREATE EXTENSION vector`, which stock images lack.
    with PostgresContainer("pgvector/pgvector:pg17") as container:
        yield container.get_connection_url().replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )


@pytest.fixture
async def session(postgres_url: str) -> AsyncGenerator[AsyncSession]:
    engine = create_async_engine(postgres_url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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


@pytest.mark.asyncio
async def test_unembedded_returns_only_chunks_without_an_embedding(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)
    added = await repo.add_batch((_chunk("a.pdf", 0), _chunk("a.pdf", 1)))
    await session.commit()
    embedded_id = added[0].id
    assert embedded_id is not None
    await repo.set_embedding(
        embedded_id, (0.1,) * constants.DOCUMENT_CHUNK_EMBEDDING_DIM
    )
    await session.commit()

    pending = await repo.unembedded(limit=10)

    assert [c.id for c in pending] == [added[1].id]


@pytest.mark.asyncio
async def test_unembedded_respects_the_limit(session: AsyncSession) -> None:
    repo = SQLDocumentChunkRepository(session)
    await repo.add_batch((_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2)))
    await session.commit()

    pending = await repo.unembedded(limit=2)

    assert len(pending) == 2


@pytest.mark.asyncio
async def test_set_embedding_round_trips_the_vector(session: AsyncSession) -> None:
    repo = SQLDocumentChunkRepository(session)
    added = await repo.add_batch((_chunk("a.pdf", 0),))
    await session.commit()
    chunk_id = added[0].id
    assert chunk_id is not None
    vector = tuple(float(i) for i in range(constants.DOCUMENT_CHUNK_EMBEDDING_DIM))

    await repo.set_embedding(chunk_id, vector)
    await session.commit()

    fetched = await repo.by_source_file("a.pdf")
    assert fetched[0].embedding == vector


@pytest.mark.asyncio
async def test_set_embedding_is_a_noop_when_chunk_missing(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)

    await repo.set_embedding(999, (0.0,) * constants.DOCUMENT_CHUNK_EMBEDDING_DIM)
    await session.commit()  # doesn't raise


def _unit_vector(index: int) -> tuple[float, ...]:
    """A one-hot vector, orthogonal to every other _unit_vector — cosine
    distance to itself is 0.0, to any other index is 1.0, so ranking
    against a query vector is deterministic and checkable."""
    dim = constants.DOCUMENT_CHUNK_EMBEDDING_DIM
    return tuple(1.0 if i == index else 0.0 for i in range(dim))


@pytest.mark.asyncio
async def test_search_by_similarity_ranks_closest_first(session: AsyncSession) -> None:
    repo = SQLDocumentChunkRepository(session)
    added = await repo.add_batch(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2))
    )
    await session.commit()
    for chunk, vector in zip(
        added, (_unit_vector(0), _unit_vector(1), _unit_vector(2)), strict=True
    ):
        assert chunk.id is not None
        await repo.set_embedding(chunk.id, vector)
    await session.commit()

    results = await repo.search_by_similarity(_unit_vector(1), top_k=3)

    assert results[0].chunk_index == 1


@pytest.mark.asyncio
async def test_search_by_similarity_respects_top_k(session: AsyncSession) -> None:
    repo = SQLDocumentChunkRepository(session)
    added = await repo.add_batch(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2))
    )
    await session.commit()
    for chunk, vector in zip(
        added, (_unit_vector(0), _unit_vector(1), _unit_vector(2)), strict=True
    ):
        assert chunk.id is not None
        await repo.set_embedding(chunk.id, vector)
    await session.commit()

    results = await repo.search_by_similarity(_unit_vector(0), top_k=1)

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_by_similarity_excludes_unembedded_chunks(
    session: AsyncSession,
) -> None:
    repo = SQLDocumentChunkRepository(session)
    await repo.add_batch((_chunk("a.pdf", 0),))
    await session.commit()

    results = await repo.search_by_similarity(_unit_vector(0), top_k=10)

    assert results == ()
