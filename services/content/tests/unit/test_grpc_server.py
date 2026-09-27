"""TermServiceServicer tests: request/reply mapping for each RPC."""

from __future__ import annotations

import pytest
from term_proto import term_pb2

from content_service.api.grpc.server import TermServiceServicer
from content_service.domain import constants
from content_service.domain.document_chunk import DocumentChunk
from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryUnitOfWork


class _LookupEmbedder:
    """Maps known query text to a fixed vector so search ranking is
    checkable without a real model."""

    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self._vectors = vectors

    async def embed(self, text: str) -> list[float]:
        return list(self._vectors[text])


def _unit_vector(index: int) -> tuple[float, ...]:
    dim = constants.DOCUMENT_CHUNK_EMBEDDING_DIM
    return tuple(1.0 if i == index else 0.0 for i in range(dim))


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )


def _servicer(
    uow: InMemoryUnitOfWork, embedder: _LookupEmbedder | None = None
) -> TermServiceServicer:
    async def get_unit_of_work():
        yield uow

    return TermServiceServicer(
        get_unit_of_work, lambda: embedder or _LookupEmbedder({})
    )


@pytest.mark.asyncio
async def test_get_random_without_category_returns_any_term(term: Term) -> None:
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term}))

    reply = await servicer.GetRandom(term_pb2.GetRandomRequest(), context=None)  # type: ignore

    assert reply.found
    assert reply.id == "uow"


@pytest.mark.asyncio
async def test_get_random_forwards_category_filter(term: Term) -> None:
    lambda_term = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    servicer = _servicer(
        InMemoryUnitOfWork(terms={term.id: term, lambda_term.id: lambda_term})
    )

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(category="python-keywords"),
        context=None,  # type: ignore
    )

    assert reply.found
    assert reply.id == "lambda"


@pytest.mark.asyncio
async def test_get_random_not_found_when_category_has_no_terms(term: Term) -> None:
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term}))

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(category="nonexistent-category"),
        context=None,  # type: ignore
    )

    assert not reply.found


@pytest.mark.asyncio
async def test_get_random_forwards_content_filters(term: Term) -> None:
    """min_difficulty/require_examples/min_definition_length all reach the
    use case — a Boss-eligible term is drawn over an ineligible one."""
    eligible = term.model_copy(
        update={
            "id": "eligible",
            "difficulty": Difficulty.HARD,
            "examples": ("An example.",),
            "definitions": ("x" * 40,),
        }
    )
    ineligible = term.model_copy(update={"id": "ineligible"})
    servicer = _servicer(
        InMemoryUnitOfWork(terms={eligible.id: eligible, ineligible.id: ineligible})
    )

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(
            min_difficulty=int(Difficulty.MODERATE),
            require_examples=True,
            min_definition_length=40,
        ),
        context=None,  # type: ignore
    )

    assert reply.found
    assert reply.id == "eligible"


@pytest.mark.asyncio
async def test_get_random_not_found_when_no_term_matches_content_filters(
    term: Term,
) -> None:
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term}))

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(require_examples=True),
        context=None,  # type: ignore
    )

    assert not reply.found


@pytest.mark.asyncio
async def test_list_categories_returns_every_distinct_slug(term: Term) -> None:
    lambda_term = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    servicer = _servicer(
        InMemoryUnitOfWork(terms={term.id: term, lambda_term.id: lambda_term})
    )

    reply = await servicer.ListCategories(
        term_pb2.ListCategoriesRequest(),
        context=None,  # type: ignore
    )

    assert tuple(reply.categories) == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_list_term_ids_returns_every_id_sorted(term: Term) -> None:
    other = term.model_copy(update={"id": "zebra"})
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term, other.id: other}))

    reply = await servicer.ListTermIds(
        term_pb2.ListTermIdsRequest(),
        context=None,  # type: ignore
    )

    assert tuple(reply.term_ids) == ("uow", "zebra")


async def _seed_embedded_chunk(
    uow: InMemoryUnitOfWork, text: str, embedding: tuple[float, ...]
) -> None:
    chunk = DocumentChunk(
        text=text,
        source_file="doc.txt",
        chunk_index=0,
        char_start=0,
        char_end=len(text),
    )
    (added,) = await uow.document_chunks.add_batch((chunk,))
    assert added.id is not None
    await uow.document_chunks.set_embedding(added.id, embedding)


@pytest.mark.asyncio
async def test_search_chunks_ranks_closest_first() -> None:
    uow = InMemoryUnitOfWork()
    await _seed_embedded_chunk(uow, "about UoW", _unit_vector(0))
    await _seed_embedded_chunk(uow, "about something else", _unit_vector(1))
    embedder = _LookupEmbedder({"UoW pattern": _unit_vector(0)})
    servicer = _servicer(uow, embedder)

    reply = await servicer.SearchChunks(
        term_pb2.SearchChunksRequest(query="UoW pattern", top_k=2),
        context=None,  # type: ignore
    )

    assert reply.chunks[0].text == "about UoW"


@pytest.mark.asyncio
async def test_search_chunks_defaults_top_k_when_unset() -> None:
    uow = InMemoryUnitOfWork()
    for i in range(constants.SEARCH_DEFAULT_TOP_K + 2):
        await _seed_embedded_chunk(uow, f"chunk {i}", _unit_vector(i))
    embedder = _LookupEmbedder({"query": _unit_vector(0)})
    servicer = _servicer(uow, embedder)

    # top_k left unset — proto3 int32 defaults to 0, which must not mean
    # "return nothing."
    reply = await servicer.SearchChunks(
        term_pb2.SearchChunksRequest(query="query"),
        context=None,  # type: ignore
    )

    assert len(reply.chunks) == constants.SEARCH_DEFAULT_TOP_K


@pytest.mark.asyncio
async def test_search_chunks_empty_corpus_returns_no_chunks() -> None:
    embedder = _LookupEmbedder({"anything": _unit_vector(0)})
    servicer = _servicer(InMemoryUnitOfWork(), embedder)

    reply = await servicer.SearchChunks(
        term_pb2.SearchChunksRequest(query="anything", top_k=5),
        context=None,  # type: ignore
    )

    assert tuple(reply.chunks) == ()
