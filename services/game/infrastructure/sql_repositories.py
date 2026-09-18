"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports import TermRepository
from domain.term import Term
from infrastructure.database import TermModel


class SQLTermRepository(TermRepository):
    """Query terms from PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_id(self, term_id: str) -> Term | None:
        """Fetch a term by ID from the database."""
        stmt = select(TermModel).where(TermModel.id == term_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        assert isinstance(model.data, str)
        data = json.loads(model.data)
        return Term(**data)
