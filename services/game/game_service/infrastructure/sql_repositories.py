"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from game_service.application.ports import RoundRepository
from game_service.domain.round import GameRound
from game_service.infrastructure.database import GameRoundModel


class SQLRoundRepository(RoundRepository):
    """Persist rounds to PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def by_id(self, round_id: str) -> GameRound | None:
        """Fetch a round by ID from the database."""
        stmt = select(GameRoundModel).where(GameRoundModel.id == round_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        assert isinstance(model.data, str)
        return GameRound.model_validate_json(model.data)

    async def save(self, round_: GameRound) -> None:
        """Upsert a round by ID."""
        stmt = insert(GameRoundModel).values(
            id=round_.id, data=round_.model_dump_json()
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={"data": stmt.excluded.data}
        )
        await self.session.execute(stmt)
