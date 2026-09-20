"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from content_service.application.ports import TermRepository
from content_service.domain.term import Term
from content_service.infrastructure.database import TermModel


class SQLTermRepository(TermRepository):
    """Query and persist terms in PostgreSQL."""

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

    async def random(self) -> Term | None:
        """Fetch a random term from the database."""
        stmt = select(TermModel).order_by(func.random()).limit(1)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        assert isinstance(model.data, str)
        data = json.loads(model.data)
        return Term(**data)

    async def upsert(self, term: Term) -> None:
        """Create the term, or replace it if the ID already exists."""
        stmt = insert(TermModel).values(id=term.id, data=term.model_dump_json())
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={"data": stmt.excluded.data}
        )
        await self.session.execute(stmt)
