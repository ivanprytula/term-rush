"""Port Protocols.

Contracts between Application and Infrastructure layers. Every service boundary
is a Protocol; implementations are swappable (SQLAlchemy, in-memory, mock).
"""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod

from game_service.domain.outcome import GradeOutcome
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import RoundMode
from game_service.domain.term import Term
from game_service.domain.term import TermFilter
from game_service.domain.term_stats import TermStats


class TermRepository(ABC):
    """Retrieve term knowledge objects."""

    @abstractmethod
    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID. None if not found."""

    @abstractmethod
    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        term_filter: TermFilter | None = None,
    ) -> Term | None:
        """Fetch a random term, avoiding excluded_ids where possible.

        category, if given, scopes the pick to terms tagged with that
        category slug (a player-chosen collection: "python-keywords",
        "abbreviations", ...). None means the whole bank, as before.

        term_filter, if given, further scopes the pick to terms meeting
        content-level constraints (e.g. TermFilter.boss_eligible()). None
        means no additional filtering.

        content-service falls back to the full matching set (category and
        term_filter still applied, excluded_ids applied) once excluded_ids
        covers every matching term, rather than failing — None only if no
        term matches category/term_filter at all.
        """

    @abstractmethod
    async def categories(self) -> tuple[str, ...]:
        """List every category slug present in the term bank — the
        collections a player can choose to play from."""

    @abstractmethod
    async def all_ids(self) -> tuple[str, ...]:
        """Every term id in the bank, sorted — the stable input Daily 20's
        seeded selection shuffles."""


class RoundRepository(ABC):
    """Persist and retrieve play-through rounds."""

    @abstractmethod
    async def by_id(self, round_id: str) -> GameRound | None:
        """Fetch a round by ID. None if not found."""

    @abstractmethod
    async def save(self, round_: GameRound) -> None:
        """Create or replace a round."""

    @abstractmethod
    async def top_by_score(
        self, limit: int, mode: RoundMode | None = None
    ) -> list[GameRound]:
        """Fetch the top `limit` rounds ordered by total_score descending.

        mode, if given, scopes the leaderboard to that mode only. None
        mixes every mode's scores (the pre-existing, now opt-out, fairness
        caveat)."""


class GradeCache(ABC):
    """Cache grading outcomes to avoid redundant LLM calls."""

    @abstractmethod
    async def get(self, term_id: str, answer_hash: str) -> GradeOutcome | None:
        """Retrieve a cached outcome. None if not cached."""

    @abstractmethod
    async def put(self, term_id: str, answer_hash: str, outcome: GradeOutcome) -> None:
        """Store an outcome."""


class TermStatsRepository(ABC):
    """Accumulate observed grading outcomes per term (ADR-0011: the
    AnswerGraded consumer). Not a UnitOfWork member: written by the Kafka
    consumer, outside any request's transaction, and read by a standalone
    stats endpoint — the same shared-instance shape as GrpcTermRepository."""

    @abstractmethod
    async def get(self, term_id: str) -> TermStats | None:
        """Fetch the tally for a term. None if no answer has been graded yet."""

    @abstractmethod
    async def record(self, term_id: str, verdict: Verdict) -> None:
        """Tally one more graded answer against the term."""


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
