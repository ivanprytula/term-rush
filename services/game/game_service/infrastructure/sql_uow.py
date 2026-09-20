"""SQLAlchemy-backed Unit of Work."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from game_service.application.ports import EventPublisher
from game_service.application.ports import TermRepository
from game_service.application.ports import UnitOfWork
from game_service.infrastructure.memory import InMemoryEventPublisher
from game_service.infrastructure.memory import InMemoryGradeCache
from game_service.infrastructure.sql_repositories import SQLSessionRepository


class SQLUnitOfWork(UnitOfWork):
    """Transaction coordinator backed by SQLAlchemy.

    Sessions live in PostgreSQL; terms come from content-service over gRPC
    (ADR-0009) — terms is a shared, long-lived repository instance passed in
    rather than constructed per-request, so its lookup cache persists across
    requests. Grade cache stays in-memory; events publish to Kafka when
    KAFKA_BROKER_URL is set (ADR-0011), a shared publisher passed in like
    terms, else fall back to an in-memory no-op.
    """

    def __init__(
        self,
        session: AsyncSession,
        terms: TermRepository,
        events: EventPublisher | None = None,
    ) -> None:
        self.session = session
        self.terms = terms
        self.sessions = SQLSessionRepository(session)
        self.grade_cache = InMemoryGradeCache()
        self.events = events if events is not None else InMemoryEventPublisher()
        self._in_transaction = False

    async def __aenter__(self) -> SQLUnitOfWork:
        self._in_transaction = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is None:
                await self.commit()
            else:
                await self.session.rollback()
        finally:
            self._in_transaction = False
            await self.session.close()

    async def commit(self) -> None:
        """Commit the transaction."""
        if not self._in_transaction:
            raise RuntimeError("Cannot commit outside a transaction")
        await self.session.commit()
