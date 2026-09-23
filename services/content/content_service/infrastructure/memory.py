"""In-memory adapters for local testing and stateless deployments."""

from __future__ import annotations

import asyncio
import random
from typing import Any

from content_service.application.ports import EventPublisher
from content_service.application.ports import ReviewQueueRepository
from content_service.application.ports import TermRepository
from content_service.application.ports import UnitOfWork
from content_service.domain.review import ReviewCandidate
from content_service.domain.review import ReviewStatus
from content_service.domain.term import Term


class InMemoryTermRepository(TermRepository):
    """Store terms in a dict."""

    def __init__(self, terms: dict[str, Term] | None = None) -> None:
        self.terms = terms or {}

    async def by_id(self, term_id: str) -> Term | None:
        return self.terms.get(term_id)

    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        min_difficulty: int | None = None,
        require_examples: bool = False,
        min_definition_length: int | None = None,
    ) -> Term | None:
        if not self.terms:
            return None
        matching = [
            t
            for t in self.terms.values()
            if (category is None or any(c.slug == category for c in t.categories))
            and (min_difficulty is None or t.difficulty >= min_difficulty)
            and (not require_examples or bool(t.examples))
            and (
                min_definition_length is None
                or len(t.primary_definition) >= min_definition_length
            )
        ]
        if not matching:
            return None
        candidates = [t for t in matching if t.id not in excluded_ids]
        return random.choice(candidates or matching)

    async def categories(self) -> tuple[str, ...]:
        slugs = {c.slug for t in self.terms.values() for c in t.categories}
        return tuple(sorted(slugs))

    async def all_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.terms.keys()))

    async def upsert(self, term: Term) -> None:
        self.terms[term.id] = term


class InMemoryReviewQueueRepository(ReviewQueueRepository):
    """Store review candidates in a dict, keyed by an auto-incrementing id."""

    def __init__(self) -> None:
        self.candidates: dict[int, ReviewCandidate] = {}
        self._next_id = 1

    async def add(self, candidate: ReviewCandidate) -> ReviewCandidate:
        assigned = candidate.model_copy(update={"id": self._next_id})
        self.candidates[self._next_id] = assigned
        self._next_id += 1
        return assigned

    async def by_id(self, candidate_id: int) -> ReviewCandidate | None:
        return self.candidates.get(candidate_id)

    async def list_by_status(self, status: ReviewStatus) -> tuple[ReviewCandidate, ...]:
        return tuple(c for c in self.candidates.values() if c.status == status)

    async def set_status(self, candidate_id: int, status: ReviewStatus) -> None:
        existing = self.candidates.get(candidate_id)
        if existing is None:
            return
        self.candidates[candidate_id] = existing.model_copy(update={"status": status})


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
        self.review_queue = InMemoryReviewQueueRepository()
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
