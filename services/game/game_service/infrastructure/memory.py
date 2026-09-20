"""In-memory adapters for local testing and stateless deployments."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from game_service.application.ports import EventPublisher
from game_service.application.ports import GradeCache
from game_service.application.ports import SessionRepository
from game_service.application.ports import TermRepository
from game_service.application.ports import UnitOfWork
from game_service.domain.outcome import GradeOutcome
from game_service.domain.session import Session
from game_service.domain.term import Term


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


class InMemorySessionRepository(SessionRepository):
    """Store sessions in a dict. Does not survive a process restart."""

    def __init__(self, sessions: dict[str, Session] | None = None) -> None:
        self.sessions = sessions or {}

    async def by_id(self, session_id: str) -> Session | None:
        return self.sessions.get(session_id)

    async def save(self, session: Session) -> None:
        self.sessions[session.id] = session


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
        sessions: dict[str, Session] | None = None,
    ) -> None:
        self.terms = InMemoryTermRepository(terms)
        self.sessions = InMemorySessionRepository(sessions)
        self.grade_cache = InMemoryGradeCache()
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
