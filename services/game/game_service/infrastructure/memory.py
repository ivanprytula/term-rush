"""In-memory adapters for local testing and stateless deployments."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from game_service.application.ports import EventPublisher
from game_service.application.ports import GradeCache
from game_service.application.ports import RoundRepository
from game_service.application.ports import TermRepository
from game_service.application.ports import TermStatsRepository
from game_service.application.ports import UnitOfWork
from game_service.domain.outcome import GradeOutcome
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.term import Term
from game_service.domain.term_stats import TermStats


class InMemoryTermRepository(TermRepository):
    """Store terms in a dict."""

    def __init__(self, terms: dict[str, Term] | None = None) -> None:
        self.terms = terms or {}

    async def by_id(self, term_id: str) -> Term | None:
        return self.terms.get(term_id)

    async def random(self, excluded_ids: frozenset[str] = frozenset()) -> Term | None:
        if not self.terms:
            return None
        candidates = [t for t in self.terms.values() if t.id not in excluded_ids]
        return random.choice(candidates or list(self.terms.values()))


class InMemoryRoundRepository(RoundRepository):
    """Store rounds in a dict. Does not survive a process restart."""

    def __init__(self, rounds: dict[str, GameRound] | None = None) -> None:
        self.rounds = rounds or {}

    async def by_id(self, round_id: str) -> GameRound | None:
        return self.rounds.get(round_id)

    async def save(self, round_: GameRound) -> None:
        self.rounds[round_.id] = round_

    async def top_by_score(self, limit: int) -> list[GameRound]:
        """Not supported: the leaderboard query is a SQL-index demonstration,
        not a feature this adapter needs to fake."""
        raise NotImplementedError("Leaderboard requires the SQL adapter")


class InMemoryGradeCache(GradeCache):
    """Cache grading outcomes in a nested dict: term_id -> answer_hash -> outcome."""

    def __init__(self) -> None:
        self.cache: dict[str, dict[str, GradeOutcome]] = {}

    async def get(self, term_id: str, answer_hash: str) -> GradeOutcome | None:
        return self.cache.get(term_id, {}).get(answer_hash)

    async def put(self, term_id: str, answer_hash: str, outcome: GradeOutcome) -> None:
        if term_id not in self.cache:
            self.cache[term_id] = {}
        self.cache[term_id][answer_hash] = outcome


class InMemoryTermStatsRepository(TermStatsRepository):
    """Tally verdicts in a dict. Does not survive a process restart."""

    def __init__(self) -> None:
        self.stats: dict[str, TermStats] = {}

    async def get(self, term_id: str) -> TermStats | None:
        return self.stats.get(term_id)

    async def record(self, term_id: str, verdict: Verdict) -> None:
        current = self.stats.get(term_id) or TermStats(term_id=term_id)
        self.stats[term_id] = current.with_verdict(verdict)


class InMemoryEventPublisher(EventPublisher):
    """Collect events in memory for testing."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class InMemoryUnitOfWork(UnitOfWork):
    """Simple async context manager backed by in-memory adapters.

    Uses asyncio.Lock for concurrent request isolation (Phase 1d in-memory cache).
    """

    def __init__(
        self,
        terms: dict[str, Term] | None = None,
        rounds: dict[str, GameRound] | None = None,
        grade_cache: GradeCache | None = None,
    ) -> None:
        self.terms = InMemoryTermRepository(terms)
        self.rounds = InMemoryRoundRepository(rounds)
        self.grade_cache = (
            grade_cache if grade_cache is not None else InMemoryGradeCache()
        )
        self.events = InMemoryEventPublisher()
        self._in_transaction = False
        self._lock: asyncio.Lock | None = None

    async def __aenter__(self) -> InMemoryUnitOfWork:
        if self._lock is None:
            self._lock = asyncio.Lock()
        await self._lock.acquire()
        self._in_transaction = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        assert self._lock is not None  # set by __aenter__, which always runs first
        try:
            if exc_type is None:
                await self.commit()
        finally:
            self._in_transaction = False
            self._lock.release()

    async def commit(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("Cannot commit outside a transaction")
