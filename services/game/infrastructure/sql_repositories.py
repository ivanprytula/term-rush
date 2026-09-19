"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from application.ports import SessionRepository
from application.ports import TermRepository
from domain.session import Session
from domain.term import Term
from infrastructure.database import SessionModel
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


class SQLSessionRepository(SessionRepository):
    """Persist sessions to PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_id(self, session_id: str) -> Session | None:
        """Fetch a session by ID from the database."""
        stmt = select(SessionModel).where(SessionModel.id == session_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        assert isinstance(model.data, str)
        return Session.model_validate_json(model.data)

    async def save(self, session: Session) -> None:
        """Upsert a session by ID."""
        stmt = insert(SessionModel).values(
            id=session.id, data=session.model_dump_json()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={"data": stmt.excluded.data}
        )
        await self.session.execute(stmt)
