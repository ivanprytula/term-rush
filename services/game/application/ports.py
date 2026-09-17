"""Port Protocols.

Contracts between Application and Infrastructure layers. Every service boundary
is a Protocol; implementations are swappable (SQLAlchemy, in-memory, mock).
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from domain.outcome import GradeOutcome
from domain.term import Term


class TermRepository(ABC):
    """Retrieve term knowledge objects."""

    @abstractmethod
    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID. None if not found."""


class GradeCache(ABC):
    """Cache grading outcomes to avoid redundant LLM calls."""

    @abstractmethod
    async def get(self, term_id: str, answer_hash: str) -> GradeOutcome | None:
        """Retrieve a cached outcome. None if not cached."""

    @abstractmethod
    async def put(self, term_id: str, answer_hash: str, outcome: GradeOutcome) -> None:
        """Store an outcome."""


class EventPublisher(ABC):
    """Publish domain events for external consumption."""

    @abstractmethod
    async def publish(self, event_type: str, payload: dict) -> None:
        """Emit an event."""


class UnitOfWork(ABC):
    """Coordinate changes across repositories in a single transaction.

    In-memory uses a global lock; SQL uses BEGIN/COMMIT; events publish on
    successful commit.
    """

    terms: TermRepository
    grade_cache: GradeCache
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
