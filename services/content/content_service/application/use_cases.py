"""Application use cases.

Pure business logic over ports; independent of Framework/Infrastructure.
"""

from __future__ import annotations

from content_service.application.ports import UnitOfWork
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

    async def execute(self, excluded_ids: frozenset[str] = frozenset()) -> Term:
        """Return a random term. Raises ValueError if the term bank is empty."""
        async with self.uow:
            term = await self.uow.terms.random(excluded_ids)
            if term is None:
                raise ValueError("No terms available")
            return term


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
