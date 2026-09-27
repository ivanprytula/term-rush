"""Retrieval quality eval: Recall@k on a labeled golden set (ADR-0012
Slice 2, skills-map.md's "Retrieval evaluation" row).

Uses the real ONNX embedder, not a fake — a fake with fixed or orthogonal
vectors would make Recall@k measure nothing. This is slower than the other
integration tests (real model inference per chunk/query) and is the one
place in the suite where that cost buys something a fake can't: proof that
embedding + cosine ranking actually retrieves the right document for a
plausible query, not just that the pipeline is wired correctly.

The corpus here is a self-contained golden set, not intake/documents/ (the
real demo corpus) — pinning the eval to inline fixtures means a change to
the demo documents can't silently break this test, and a change to this
test's expectations is a deliberate, reviewable diff.
"""

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

from content_service.application.use_cases import EmbedDocumentChunks
from content_service.application.use_cases import IngestDocumentChunks
from content_service.application.use_cases import SearchChunksBySimilarity
from content_service.domain.document_chunk import DocumentChunk
from content_service.infrastructure.database import Base
from content_service.infrastructure.onnx_embedder import OnnxEmbedder
from content_service.infrastructure.sql_uow import SQLUnitOfWork

pytestmark = pytest.mark.docker

# One short passage per topic, standing in for intake/documents/'s longer
# prose — enough text for embeddings to differentiate topics, short enough
# to keep this test's runtime reasonable (one real model call per chunk).
_CORPUS: dict[str, str] = {
    "gil.txt": (
        "The Global Interpreter Lock, GIL, is a mutex in CPython that "
        "allows only one thread to execute Python bytecode at a time. "
        "This prevents true CPU-bound parallelism from multithreading, "
        "though I/O-bound work still benefits because CPython releases "
        "the GIL during blocking calls like network reads."
    ),
    "descriptor_protocol.txt": (
        "The descriptor protocol lets an object customize attribute "
        "access on another class via __get__, __set__, and __delete__. "
        "property, staticmethod, and classmethod are all descriptors, "
        "which is how they intercept normal attribute lookup."
    ),
    "mro.txt": (
        "The Method Resolution Order, MRO, is the linearized sequence "
        "Python follows when searching a class hierarchy for an "
        "attribute. super() calls the next class in the MRO, not "
        "necessarily the immediate parent, which matters for cooperative "
        "multiple inheritance in diamond hierarchies."
    ),
    "cookies.txt": (
        "Chocolate chip cookies are made by creaming butter and sugar, "
        "then mixing in eggs, vanilla, flour, and chocolate chips before "
        "baking at 350 degrees for about ten minutes."
    ),
}

# (query, expected top-1 source file) — a query written the way a grading
# context lookup would phrase it (term + expansion, per LLMRubricGrader's
# _retrieve_context), not a copy-paste of the corpus text itself.
_GOLDEN_SET: tuple[tuple[str, str], ...] = (
    ("GIL Global Interpreter Lock", "gil.txt"),
    ("threading and the GIL in CPython", "gil.txt"),
    ("descriptor protocol attribute access", "descriptor_protocol.txt"),
    ("property staticmethod classmethod", "descriptor_protocol.txt"),
    ("Method Resolution Order MRO", "mro.txt"),
    ("super() multiple inheritance diamond", "mro.txt"),
)

# Recall@k here means: is the expected source file among the sources of
# the top-k results. 1.0 (perfect) is achievable on a 4-document corpus
# this distinct in topic; the threshold leaves slack for embedding-model
# variance without masking a real regression (e.g. a broken chunker, a
# swapped embedding model, a corrupted index).
RECALL_AT_K = 3
MIN_RECALL = 0.8


@pytest.fixture(scope="module")
def postgres_url() -> Generator[str]:
    with PostgresContainer("pgvector/pgvector:pg17") as container:
        yield container.get_connection_url().replace(
            "postgresql+psycopg2", "postgresql+asyncpg"
        )


@pytest.fixture(scope="module")
def embedder() -> OnnxEmbedder:
    return OnnxEmbedder()


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


@pytest.fixture
async def uow(session: AsyncSession) -> SQLUnitOfWork:
    return SQLUnitOfWork(session)


@pytest.fixture
async def indexed_corpus(uow: SQLUnitOfWork, embedder: OnnxEmbedder) -> None:
    """Ingest and embed the golden corpus once per test."""
    chunks = tuple(
        DocumentChunk(
            text=text_,
            source_file=source_file,
            chunk_index=0,
            char_start=0,
            char_end=len(text_),
        )
        for source_file, text_ in _CORPUS.items()
    )
    await IngestDocumentChunks(uow).execute(chunks)
    await EmbedDocumentChunks(uow, embedder).execute(batch_size=len(chunks))


@pytest.mark.asyncio
async def test_recall_at_k_meets_the_minimum_threshold(
    uow: SQLUnitOfWork,
    embedder: OnnxEmbedder,
    indexed_corpus: None,  # noqa: ARG001 — fixture runs for its side effect
) -> None:
    """The core eval: for each golden query, is the expected source among
    the top-k retrieved chunks' sources? Reports which queries missed on
    failure, not just a bare assertion, so a regression is diagnosable
    from CI output alone."""
    search = SearchChunksBySimilarity(uow, embedder)
    misses: list[str] = []

    for query, expected_source in _GOLDEN_SET:
        results = await search.execute(query, top_k=RECALL_AT_K)
        retrieved_sources = {c.source_file for c in results}
        if expected_source not in retrieved_sources:
            misses.append(
                f"{query!r} expected {expected_source!r}, got {retrieved_sources}"
            )

    recall = (len(_GOLDEN_SET) - len(misses)) / len(_GOLDEN_SET)
    assert recall >= MIN_RECALL, (
        f"Recall@{RECALL_AT_K} = {recall:.2f}, below {MIN_RECALL}. Misses:\n"
        + "\n".join(misses)
    )


@pytest.mark.asyncio
async def test_off_topic_query_does_not_retrieve_unrelated_chunks(
    uow: SQLUnitOfWork,
    embedder: OnnxEmbedder,
    indexed_corpus: None,  # noqa: ARG001 — fixture runs for its side effect
) -> None:
    """A sanity check in the other direction: a query about cookies
    should not surface as the top result for a CS query, and vice versa —
    proves the embedding space actually separates unrelated topics, not
    just that GIL-flavored queries happen to retrieve gil.txt."""
    search = SearchChunksBySimilarity(uow, embedder)

    results = await search.execute("baking cookies with chocolate chips", top_k=1)

    assert len(results) == 1
    assert results[0].source_file == "cookies.txt"
