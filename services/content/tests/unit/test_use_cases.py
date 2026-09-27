"""Application use case tests."""

from __future__ import annotations

import pytest

from content_service.application.use_cases import ApproveReviewCandidate
from content_service.application.use_cases import EmbedDocumentChunks
from content_service.application.use_cases import GetRandomTerm
from content_service.application.use_cases import GetTermById
from content_service.application.use_cases import IngestDocumentChunks
from content_service.application.use_cases import ListCategories
from content_service.application.use_cases import ListDocumentChunksBySource
from content_service.application.use_cases import ListReviewCandidates
from content_service.application.use_cases import PublishTerm
from content_service.application.use_cases import RejectReviewCandidate
from content_service.application.use_cases import SearchChunksBySimilarity
from content_service.application.use_cases import SubmitReviewCandidate
from content_service.domain import constants
from content_service.domain.document_chunk import DocumentChunk
from content_service.domain.review import ReviewCandidateNotPending
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryEventPublisher
from content_service.infrastructure.memory import InMemoryUnitOfWork


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )


@pytest.fixture
def uow(term: Term) -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork(terms={term.id: term})


@pytest.mark.asyncio
async def test_get_term_by_id_returns_the_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetTermById(uow)

    assert await use_case.execute(term.id) == term


@pytest.mark.asyncio
async def test_get_term_by_id_raises_when_missing(uow: InMemoryUnitOfWork) -> None:
    use_case = GetTermById(uow)

    with pytest.raises(ValueError, match="not found"):
        await use_case.execute("nonexistent")


@pytest.mark.asyncio
async def test_get_random_term_returns_the_only_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetRandomTerm(uow)

    assert await use_case.execute() == term


@pytest.mark.asyncio
async def test_get_random_term_raises_when_bank_is_empty() -> None:
    use_case = GetRandomTerm(InMemoryUnitOfWork())

    with pytest.raises(ValueError, match="No terms available"):
        await use_case.execute()


@pytest.mark.asyncio
async def test_get_random_term_avoids_excluded_ids(term: Term) -> None:
    other = term.model_copy(update={"id": "cqrs", "term": "CQRS"})
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(frozenset({term.id}))

    assert result.id == other.id


@pytest.mark.asyncio
async def test_get_random_term_falls_back_once_all_ids_excluded(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(frozenset({term.id}))

    assert result == term


@pytest.mark.asyncio
async def test_get_random_term_scopes_to_category(term: Term) -> None:
    other = term.model_copy(
        update={
            "id": "lambda",
            "term": "lambda",
            "categories": (Category(slug="python-keywords"),),
        }
    )
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = GetRandomTerm(uow)

    result = await use_case.execute(category="python-keywords")

    assert result == other


@pytest.mark.asyncio
async def test_get_random_term_raises_when_category_has_no_terms(
    uow: InMemoryUnitOfWork,
) -> None:
    use_case = GetRandomTerm(uow)

    with pytest.raises(ValueError, match="No terms available"):
        await use_case.execute(category="nonexistent-category")


@pytest.mark.asyncio
async def test_list_categories_returns_every_distinct_slug(term: Term) -> None:
    other = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    uow = InMemoryUnitOfWork(terms={term.id: term, other.id: other})
    use_case = ListCategories(uow)

    assert await use_case.execute() == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_publish_term_upserts_and_returns_it() -> None:
    uow = InMemoryUnitOfWork()
    new_term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    result = await use_case.execute(new_term)

    assert result == new_term
    assert await uow.terms.by_id("fsm") == new_term


@pytest.mark.asyncio
async def test_publish_term_publishes_term_published_event() -> None:
    uow = InMemoryUnitOfWork()
    term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    await use_case.execute(term)

    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert events.events == [("TermPublished", {"term_id": "fsm"})]


@pytest.mark.asyncio
async def test_submit_review_candidate_lands_pending(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    use_case = SubmitReviewCandidate(uow)

    candidate = await use_case.execute(
        term=term,
        source_type="dependency_manifest",
        source_file="pyproject.toml",
        confidence="high",
    )

    assert candidate.id is not None
    assert candidate.status == ReviewStatus.PENDING
    assert candidate.term == term
    # Never auto-promoted, regardless of confidence.
    assert await uow.terms.by_id(term.id) is None


@pytest.mark.asyncio
async def test_list_review_candidates_filters_by_status(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    await SubmitReviewCandidate(uow).execute(term, "dependency_manifest", "x", "high")

    pending = await ListReviewCandidates(uow).execute(ReviewStatus.PENDING)
    approved = await ListReviewCandidates(uow).execute(ReviewStatus.APPROVED)

    assert len(pending) == 1
    assert approved == ()


def _chunk(source_file: str = "contract.pdf", chunk_index: int = 0) -> DocumentChunk:
    return DocumentChunk(
        text=f"chunk {chunk_index}",
        source_file=source_file,
        chunk_index=chunk_index,
        char_start=chunk_index * 100,
        char_end=chunk_index * 100 + 50,
    )


@pytest.mark.asyncio
async def test_ingest_document_chunks_assigns_ids() -> None:
    uow = InMemoryUnitOfWork()
    use_case = IngestDocumentChunks(uow)

    ingested = await use_case.execute((_chunk(chunk_index=0), _chunk(chunk_index=1)))

    assert all(c.id is not None for c in ingested)


@pytest.mark.asyncio
async def test_list_document_chunks_by_source_returns_only_matching() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("b.pdf", 0))
    )

    fetched = await ListDocumentChunksBySource(uow).execute("a.pdf")

    assert len(fetched) == 2
    assert all(c.source_file == "a.pdf" for c in fetched)


@pytest.mark.asyncio
async def test_reingest_document_chunks_replaces_the_prior_batch() -> None:
    """Re-ingesting a source file supersedes its old chunks rather than
    conflicting with them - the whole point of replace semantics."""
    uow = InMemoryUnitOfWork()
    use_case = IngestDocumentChunks(uow)
    await use_case.execute((_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2)))

    await use_case.execute((_chunk("a.pdf", 0),))

    fetched = await ListDocumentChunksBySource(uow).execute("a.pdf")
    assert len(fetched) == 1


@pytest.mark.asyncio
async def test_reingest_document_chunks_leaves_other_sources_untouched() -> None:
    uow = InMemoryUnitOfWork()
    use_case = IngestDocumentChunks(uow)
    await use_case.execute((_chunk("a.pdf", 0), _chunk("b.pdf", 0)))

    await use_case.execute((_chunk("a.pdf", 0), _chunk("a.pdf", 1)))

    fetched = await ListDocumentChunksBySource(uow).execute("b.pdf")
    assert len(fetched) == 1


@pytest.mark.asyncio
async def test_approve_review_candidate_publishes_the_term(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None

    published = await ApproveReviewCandidate(uow).execute(candidate.id)

    assert published == term
    assert await uow.terms.by_id(term.id) == term
    approved = await uow.review_queue.by_id(candidate.id)
    assert approved is not None
    assert approved.status == ReviewStatus.APPROVED
    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert events.events == [("TermPublished", {"term_id": term.id})]


@pytest.mark.asyncio
async def test_approve_review_candidate_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="not found"):
        await ApproveReviewCandidate(InMemoryUnitOfWork()).execute(999)


@pytest.mark.asyncio
async def test_approve_review_candidate_raises_when_not_pending(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None
    await ApproveReviewCandidate(uow).execute(candidate.id)

    with pytest.raises(ReviewCandidateNotPending) as exc_info:
        await ApproveReviewCandidate(uow).execute(candidate.id)
    assert exc_info.value.candidate_id == candidate.id
    assert exc_info.value.status == ReviewStatus.APPROVED


@pytest.mark.asyncio
async def test_reject_review_candidate_never_publishes(term: Term) -> None:
    uow = InMemoryUnitOfWork()
    candidate = await SubmitReviewCandidate(uow).execute(
        term, "dependency_manifest", "x", "high"
    )
    assert candidate.id is not None

    await RejectReviewCandidate(uow).execute(candidate.id)

    rejected = await uow.review_queue.by_id(candidate.id)
    assert rejected is not None
    assert rejected.status == ReviewStatus.REJECTED
    assert await uow.terms.by_id(term.id) is None


@pytest.mark.asyncio
async def test_reject_review_candidate_raises_when_missing() -> None:
    with pytest.raises(ValueError, match="not found"):
        await RejectReviewCandidate(InMemoryUnitOfWork()).execute(999)


class _FakeEmbedder:
    """Deterministic stub: embeds each call, records what it was asked to
    embed so tests can assert on call order/content without a real model."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return [0.0] * constants.DOCUMENT_CHUNK_EMBEDDING_DIM


@pytest.mark.asyncio
async def test_embed_document_chunks_embeds_the_backlog() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute((_chunk("a.pdf", 0), _chunk("a.pdf", 1)))
    embedder = _FakeEmbedder()

    embedded = await EmbedDocumentChunks(uow, embedder).execute()

    assert len(embedded) == 2
    assert all(c.embedding is not None for c in embedded)
    assert sorted(embedder.calls) == ["chunk 0", "chunk 1"]


@pytest.mark.asyncio
async def test_embed_document_chunks_persists_the_embedding() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute((_chunk("a.pdf", 0),))

    await EmbedDocumentChunks(uow, _FakeEmbedder()).execute()

    fetched = await ListDocumentChunksBySource(uow).execute("a.pdf")
    assert fetched[0].embedding is not None
    assert len(fetched[0].embedding) == constants.DOCUMENT_CHUNK_EMBEDDING_DIM


@pytest.mark.asyncio
async def test_embed_document_chunks_skips_already_embedded() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute((_chunk("a.pdf", 0),))
    embedder = _FakeEmbedder()
    await EmbedDocumentChunks(uow, embedder).execute()

    second_pass = await EmbedDocumentChunks(uow, embedder).execute()

    assert second_pass == ()
    assert len(embedder.calls) == 1


@pytest.mark.asyncio
async def test_embed_document_chunks_respects_batch_size() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2))
    )

    embedded = await EmbedDocumentChunks(uow, _FakeEmbedder()).execute(batch_size=2)

    assert len(embedded) == 2


@pytest.mark.asyncio
async def test_embed_document_chunks_returns_empty_when_nothing_pending() -> None:
    uow = InMemoryUnitOfWork()

    embedded = await EmbedDocumentChunks(uow, _FakeEmbedder()).execute()

    assert embedded == ()


class _LookupEmbedder:
    """Maps known text to fixed, distinguishable vectors so ranking is
    checkable — a real model's actual output would make expected order
    unpredictable without asserting on the model itself."""

    def __init__(self, vectors: dict[str, tuple[float, ...]]) -> None:
        self._vectors = vectors

    async def embed(self, text: str) -> list[float]:
        return list(self._vectors[text])


_DIM = constants.DOCUMENT_CHUNK_EMBEDDING_DIM


def _unit_vector(index: int) -> tuple[float, ...]:
    """A one-hot vector — orthogonal to every other _unit_vector, so cosine
    distance between two different indices is always 1.0 (maximally
    dissimilar) and 0.0 to itself (identical)."""
    return tuple(1.0 if i == index else 0.0 for i in range(_DIM))


@pytest.mark.asyncio
async def test_search_chunks_by_similarity_ranks_closest_first() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2))
    )
    fixed = _LookupEmbedder(
        {
            "chunk 0": _unit_vector(0),
            "chunk 1": _unit_vector(1),
            "chunk 2": _unit_vector(2),
        }
    )
    await EmbedDocumentChunks(uow, fixed).execute()
    query_embedder = _LookupEmbedder({"query": _unit_vector(1)})

    results = await SearchChunksBySimilarity(uow, query_embedder).execute(
        "query", top_k=3
    )

    assert [c.text for c in results][0] == "chunk 1"


@pytest.mark.asyncio
async def test_search_chunks_by_similarity_respects_top_k() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute(
        (_chunk("a.pdf", 0), _chunk("a.pdf", 1), _chunk("a.pdf", 2))
    )
    fixed = _LookupEmbedder(
        {
            "chunk 0": _unit_vector(0),
            "chunk 1": _unit_vector(1),
            "chunk 2": _unit_vector(2),
        }
    )
    await EmbedDocumentChunks(uow, fixed).execute()
    query_embedder = _LookupEmbedder({"query": _unit_vector(0)})

    results = await SearchChunksBySimilarity(uow, query_embedder).execute(
        "query", top_k=1
    )

    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_chunks_by_similarity_excludes_unembedded_chunks() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute((_chunk("a.pdf", 0),))
    query_embedder = _LookupEmbedder({"query": _unit_vector(0)})

    results = await SearchChunksBySimilarity(uow, query_embedder).execute("query")

    assert results == ()


@pytest.mark.asyncio
async def test_search_chunks_by_similarity_defaults_top_k() -> None:
    uow = InMemoryUnitOfWork()
    await IngestDocumentChunks(uow).execute(
        tuple(_chunk("a.pdf", i) for i in range(constants.SEARCH_DEFAULT_TOP_K + 2))
    )
    fixed = _LookupEmbedder(
        {
            f"chunk {i}": _unit_vector(i)
            for i in range(constants.SEARCH_DEFAULT_TOP_K + 2)
        }
    )
    await EmbedDocumentChunks(uow, fixed).execute(
        batch_size=constants.SEARCH_DEFAULT_TOP_K + 2
    )
    query_embedder = _LookupEmbedder({"query": _unit_vector(0)})

    results = await SearchChunksBySimilarity(uow, query_embedder).execute("query")

    assert len(results) == constants.SEARCH_DEFAULT_TOP_K
