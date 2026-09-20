"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from game_service.application.ports import SessionRepository
from game_service.domain.session import Session
from game_service.infrastructure.database import SessionModel


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
