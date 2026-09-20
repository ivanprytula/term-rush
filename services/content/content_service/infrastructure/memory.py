"""In-memory adapters for local testing and stateless deployments."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from content_service.application.ports import EventPublisher
from content_service.application.ports import TermRepository
from content_service.application.ports import UnitOfWork
from content_service.domain.term import Term


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

    async def upsert(self, term: Term) -> None:
        self.terms[term.id] = term


class InMemoryEventPublisher(EventPublisher):
    """Collect events in memory for testing."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, event_type: str, payload: dict) -> None:
        self.events.append((event_type, payload))


class InMemoryUnitOfWork(UnitOfWork):
    """Simple async context manager backed by in-memory adapters.

    Uses asyncio.Lock for concurrent request isolation.
    """

    def __init__(self, terms: dict[str, Term] | None = None) -> None:
        self.terms = InMemoryTermRepository(terms)
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
