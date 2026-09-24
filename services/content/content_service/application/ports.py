"""Port Protocols.

Contracts between Application and Infrastructure layers. Every boundary is an
ABC; implementations are swappable (SQLAlchemy, in-memory, mock).
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from content_service.domain.document_chunk import DocumentChunk
from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Term


class TermRepository(ABC):
    """Read and write term knowledge objects."""

    @abstractmethod
    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID. None if not found."""

    @abstractmethod
    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        min_difficulty: int | None = None,
        require_examples: bool = False,
        min_definition_length: int | None = None,
    ) -> Term | None:
        """Fetch a random term, avoiding excluded_ids where possible.

        category, if given, scopes the pick to terms tagged with that
        category slug. None means the whole bank, as before.

        min_difficulty/require_examples/min_definition_length are plain
        content-property constraints — deliberately not a "Boss Round"
        concept. The caller (game-service, over gRPC) decides what a mode
        needs; content-service just filters on properties it already owns.

        Falls back to the full matching set (excluded_ids ignored, every
        other filter still applied) once every matching term is excluded,
        rather than returning None — a round that has shown every term in
        its chosen scope should repeat, not error. None only if no term
        matches at all (or the bank itself is empty, when unfiltered).
        """

    @abstractmethod
    async def categories(self) -> tuple[str, ...]:
        """List every category slug present in the term bank."""

    @abstractmethod
    async def all_ids(self) -> tuple[str, ...]:
        """Every term id in the bank, sorted. The stable input a seeded
        daily selection shuffles — sorted because an unstable order would
        change the day's puzzle."""

    @abstractmethod
    async def upsert(self, term: Term) -> None:
        """Create a term, or replace it if the ID already exists."""


class ReviewQueueRepository(ABC):
    """Read and write the pending-review candidate queue."""

    @abstractmethod
    async def add(self, candidate: ReviewCandidate) -> ReviewCandidate:
        """Insert a candidate as pending. Returns it with its assigned id."""

    @abstractmethod
    async def by_id(self, candidate_id: int) -> ReviewCandidate | None:
        """Fetch a candidate by its queue id. None if not found."""

    @abstractmethod
    async def list_by_status(self, status: ReviewStatus) -> tuple[ReviewCandidate, ...]:
        """Every candidate in the given status, oldest first."""

    @abstractmethod
    async def set_status(self, candidate_id: int, status: ReviewStatus) -> None:
        """Transition a candidate's status. No-op if the id doesn't exist —
        callers check existence via by_id first when they need to know."""


class DocumentChunkRepository(ABC):
    """Persist document chunks: the RAG/analytics corpus (ADR-0018)."""

    @abstractmethod
    async def add_batch(
        self, chunks: tuple[DocumentChunk, ...]
    ) -> tuple[DocumentChunk, ...]:
        """Insert every chunk. Returns them with assigned ids, same order."""

    @abstractmethod
    async def by_source_file(self, source_file: str) -> tuple[DocumentChunk, ...]:
        """Every chunk from one source document, in chunk_index order."""

    @abstractmethod
    async def delete_by_source_file(self, source_file: str) -> None:
        """Remove every chunk from one source document. No-op if none exist."""


class EventPublisher(ABC):
    """Publish domain events for external consumption."""

    @abstractmethod
    async def publish(self, event_type: str, payload: dict) -> None:
        """Emit an event. event_type labels the event (goes into the
        envelope, e.g. "TermPublished"); it does not select a destination —
        each adapter instance publishes to one fixed topic (its TOPIC
        constant). A publisher handling more than one topic would need
        event_type to route, which none does today."""


class UnitOfWork(ABC):
    """Coordinate changes across repositories in a single transaction.

    In-memory uses a global lock; SQL uses BEGIN/COMMIT; events publish on
    successful commit.
    """

    terms: TermRepository
    review_queue: ReviewQueueRepository
    document_chunks: DocumentChunkRepository
    events: EventPublisher

    @abstractmethod
    async def __aenter__(self) -> UnitOfWork:
        """Begin a transaction."""

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Commit on success, rollback on exception."""

    @abstractmethod
    async def commit(self) -> None:
        """Explicitly commit pending events."""
