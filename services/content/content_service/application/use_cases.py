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

    async def execute(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        min_difficulty: int | None = None,
        require_examples: bool = False,
        min_definition_length: int | None = None,
    ) -> Term:
        """Return a random term, optionally scoped to a category and/or
        content-property constraints. Raises ValueError if no term matches."""
        async with self.uow:
            term = await self.uow.terms.random(
                excluded_ids,
                category,
                min_difficulty,
                require_examples,
                min_definition_length,
            )
            if term is None:
                raise ValueError("No terms available")
            return term


class ListCategories:
    """List every category slug present in the term bank."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self) -> tuple[str, ...]:
        """Return every category slug, sorted."""
        async with self.uow:
            return await self.uow.terms.categories()


class ListAllTermIds:
    """List every term id in the bank — the stable input a seeded daily
    selection (game-service's Daily 20) shuffles."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self) -> tuple[str, ...]:
        """Return every term id, sorted."""
        async with self.uow:
            return await self.uow.terms.all_ids()


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
