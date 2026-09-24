"""SQLAlchemy-backed Unit of Work."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from content_service.application.ports import EventPublisher
from content_service.application.ports import UnitOfWork
from content_service.infrastructure.memory import InMemoryEventPublisher
from content_service.infrastructure.sql_repositories import SQLReviewQueueRepository
from content_service.infrastructure.sql_repositories import SQLTermRepository


class SQLUnitOfWork(UnitOfWork):
    """Transaction coordinator backed by SQLAlchemy.

    Events publish to Kafka when KAFKA_BROKER_URL is set (ADR-0011), a
    shared publisher passed in, else fall back to an in-memory no-op.
    """

    def __init__(
        self, session: AsyncSession, events: EventPublisher | None = None
    ) -> None:
        self.session = session
        self.terms = SQLTermRepository(session)
        self.review_queue = SQLReviewQueueRepository(session)
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
