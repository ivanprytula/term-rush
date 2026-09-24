"""Application use cases.

Pure business logic over ports; independent of Framework/Infrastructure.
"""

from __future__ import annotations

from content_service.application.ports import UnitOfWork
from content_service.domain.document_chunk import DocumentChunk
from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewCandidateNotPending
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Term


class GetTermById:
    """Fetch a single term by ID."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, term_id: str) -> Term:
        """Return the term. Raises ValueError if it doesn't exist."""
        async with self.uow:
            term = await self.uow.terms.by_id(term_id)
            if term is None:
                raise ValueError(f"Term not found: {term_id}")
            return term


class GetRandomTerm:
    """Fetch a random term, avoiding a caller-supplied exclusion set."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        min_difficulty: int | None = None,
        require_examples: bool = False,
        min_definition_length: int | None = None,
    ) -> Term:
        """Return a random term, optionally scoped to a category and/or
        content-property constraints. Raises ValueError if no term matches."""
        async with self.uow:
            term = await self.uow.terms.random(
                excluded_ids,
                category,
                min_difficulty,
                require_examples,
                min_definition_length,
            )
            if term is None:
                raise ValueError("No terms available")
            return term


class ListCategories:
    """List every category slug present in the term bank."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self) -> tuple[str, ...]:
        """Return every category slug, sorted."""
        async with self.uow:
            return await self.uow.terms.categories()


class ListAllTermIds:
    """List every term id in the bank — the stable input a seeded daily
    selection (game-service's Daily 20) shuffles."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self) -> tuple[str, ...]:
        """Return every term id, sorted."""
        async with self.uow:
            return await self.uow.terms.all_ids()


class PublishTerm:
    """Create a term, or replace it if the ID already exists.

    Publishes a TermPublished event on success — the hook game-service's
    cache invalidation consumes (Kafka wiring lands in a later increment;
    the event fires against a no-op publisher until then).
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, term: Term) -> Term:
        """Upsert the term and publish TermPublished. Returns the term."""
        async with self.uow:
            await self.uow.terms.upsert(term)
            await self.uow.events.publish("TermPublished", {"term_id": term.id})
            return term


class IngestDocumentChunks:
    """Persist a batch of chunked document text (ADR-0018 Slice 1: the RAG
    corpus, no embeddings yet).

    Replace semantics per source file: re-ingesting a document (a pipeline
    retry, or a re-chunk after tuning chunk size) deletes that document's
    existing chunks first, so it can't conflict with the
    (source_file, chunk_index) unique constraint. A document's chunk set
    is fully superseded, not merged chunk-by-chunk.

    No review gate — unlike terms, chunks are raw ingested text, not
    LLM-authored knowledge published to players. The review gate exists to
    protect what the game teaches, which doesn't apply here.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self, chunks: tuple[DocumentChunk, ...]
    ) -> tuple[DocumentChunk, ...]:
        source_files = {chunk.source_file for chunk in chunks}
        async with self.uow:
            for source_file in source_files:
                await self.uow.document_chunks.delete_by_source_file(source_file)
            return await self.uow.document_chunks.add_batch(chunks)


class ListDocumentChunksBySource:
    """List every chunk ingested from one source document, in order."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, source_file: str) -> tuple[DocumentChunk, ...]:
        async with self.uow:
            return await self.uow.document_chunks.by_source_file(source_file)


class SubmitReviewCandidate:
    """Queue a pipeline-enriched candidate for human review.

    Always lands as PENDING — a candidate is never auto-promoted here,
    regardless of source confidence (ADR-0004: an agent writing to the
    live term bank unreviewed is a liability).
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self, term: Term, source_type: str, source_file: str, confidence: str
    ) -> ReviewCandidate:
        candidate = ReviewCandidate(
            term=term,
            source_type=source_type,
            source_file=source_file,
            confidence=confidence,
        )
        async with self.uow:
            return await self.uow.review_queue.add(candidate)


class ListReviewCandidates:
    """List review candidates by status, for the human review surface."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, status: ReviewStatus) -> tuple[ReviewCandidate, ...]:
        async with self.uow:
            return await self.uow.review_queue.list_by_status(status)


class ApproveReviewCandidate:
    """Promote a pending candidate into the live term bank.

    Reuses PublishTerm's upsert + TermPublished event — approval is
    publication, just gated by a human decision instead of a direct
    author call.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, candidate_id: int) -> Term:
        """Approve and publish the candidate's term. Raises ValueError if
        the candidate doesn't exist, or ReviewCandidateNotPending if it's
        already been approved or rejected."""
        async with self.uow:
            candidate = await self.uow.review_queue.by_id(candidate_id)
            if candidate is None:
                raise ValueError(f"Review candidate not found: {candidate_id}")
            if candidate.status != ReviewStatus.PENDING:
                raise ReviewCandidateNotPending(candidate_id, candidate.status)
            await self.uow.terms.upsert(candidate.term)
            await self.uow.review_queue.set_status(candidate_id, ReviewStatus.APPROVED)
            await self.uow.events.publish(
                "TermPublished", {"term_id": candidate.term.id}
            )
            return candidate.term


class RejectReviewCandidate:
    """Reject a pending candidate. It never reaches the live term bank."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, candidate_id: int) -> None:
        """Raises ValueError if the candidate doesn't exist, or
        ReviewCandidateNotPending if it's already been approved or
        rejected."""
        async with self.uow:
            candidate = await self.uow.review_queue.by_id(candidate_id)
            if candidate is None:
                raise ValueError(f"Review candidate not found: {candidate_id}")
            if candidate.status != ReviewStatus.PENDING:
                raise ReviewCandidateNotPending(candidate_id, candidate.status)
            await self.uow.review_queue.set_status(candidate_id, ReviewStatus.REJECTED)
