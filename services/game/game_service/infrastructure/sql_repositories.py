"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

from sqlalchemy import desc
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from game_service.application.ports import RoundRepository
from game_service.application.ports import TermStatsRepository
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.term_stats import TermStats
from game_service.infrastructure.database import GameRoundModel
from game_service.infrastructure.database import TermStatsModel


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
            id=round_.id,
            data=round_.model_dump_json(),
            total_score=round_.total_score,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"],
            set_={"data": stmt.excluded.data, "total_score": stmt.excluded.total_score},
        )
        await self.session.execute(stmt)

    async def top_by_score(self, limit: int) -> list[GameRound]:
        """Fetch the top rounds by total_score, sorted in SQL via the
        indexed column rather than deserializing every row's JSON."""
        stmt = (
            select(GameRoundModel)
            .order_by(desc(GameRoundModel.total_score))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return [GameRound.model_validate_json(m.data) for m in result.scalars()]


class SQLTermStatsRepository(TermStatsRepository):
    """Persist per-term verdict tallies to PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, term_id: str) -> TermStats | None:
        stmt = select(TermStatsModel).where(TermStatsModel.term_id == term_id)
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        return TermStats(
            term_id=model.term_id,
            correct_count=model.correct_count,
            partial_count=model.partial_count,
            incorrect_count=model.incorrect_count,
        )

    async def record(self, term_id: str, verdict: Verdict) -> None:
        """Upsert-increment in one statement: concurrent consumers tallying
        the same term must not lose an update to a read-modify-write race."""
        column = f"{verdict.value}_count"
        stmt = insert(TermStatsModel).values(term_id=term_id, **{column: 1})
        stmt = stmt.on_conflict_do_update(
            index_elements=["term_id"],
            set_={column: getattr(TermStatsModel, column) + 1},
        )
        await self.session.execute(stmt)
