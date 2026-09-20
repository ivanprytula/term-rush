"""Port Protocols.

Contracts between Application and Infrastructure layers. Every boundary is an
ABC; implementations are swappable (SQLAlchemy, in-memory, mock).
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from content_service.domain.term import Term


class TermRepository(ABC):
    """Read and write term knowledge objects."""

    @abstractmethod
    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID. None if not found."""

    @abstractmethod
    async def random(self) -> Term | None:
        """Fetch a random term. None if the term bank is empty."""

    @abstractmethod
    async def upsert(self, term: Term) -> None:
        """Create a term, or replace it if the ID already exists."""


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
