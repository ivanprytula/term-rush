"""SQLAlchemy-backed Unit of Work."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from application.ports import UnitOfWork
from infrastructure.memory import InMemoryEventPublisher
from infrastructure.memory import InMemoryGradeCache
from infrastructure.sql_repositories import SQLTermRepository


class SQLUnitOfWork(UnitOfWork):
    """Transaction coordinator backed by SQLAlchemy.

    Grade cache and events remain in-memory for Phase 1; PostgreSQL for terms only.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.terms = SQLTermRepository(session)
        self.grade_cache = InMemoryGradeCache()
        self.events = InMemoryEventPublisher()
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
