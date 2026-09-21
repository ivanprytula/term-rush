"""Port Protocols.

Contracts between Application and Infrastructure layers. Every service boundary
is a Protocol; implementations are swappable (SQLAlchemy, in-memory, mock).
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from game_service.domain.outcome import GradeOutcome
from game_service.domain.round import GameRound
from game_service.domain.term import Term


class TermRepository(ABC):
    """Retrieve term knowledge objects."""

    @abstractmethod
    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID. None if not found."""

    @abstractmethod
    async def random(self, excluded_ids: frozenset[str] = frozenset()) -> Term | None:
        """Fetch a random term, avoiding excluded_ids where possible.

        content-service falls back to the full bank once excluded_ids
        covers every term, rather than failing — None only if the bank
        itself is empty.
        """


class RoundRepository(ABC):
    """Persist and retrieve play-through rounds."""

    @abstractmethod
    async def by_id(self, round_id: str) -> GameRound | None:
        """Fetch a round by ID. None if not found."""

    @abstractmethod
    async def save(self, round_: GameRound) -> None:
        """Create or replace a round."""

    @abstractmethod
    async def top_by_score(self, limit: int) -> list[GameRound]:
        """Fetch the top `limit` rounds ordered by total_score descending."""


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
        """Emit an event. event_type labels the event (goes into the
        envelope, e.g. "AnswerGraded"); it does not select a destination —
        each adapter instance publishes to one fixed topic (its TOPIC
        constant). A publisher handling more than one topic would need
        event_type to route, which none does today."""


class UnitOfWork(ABC):
    """Coordinate changes across repositories in a single transaction.

    In-memory uses a global lock; SQL uses BEGIN/COMMIT; events publish on
    successful commit.
    """

    terms: TermRepository
    rounds: RoundRepository
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
