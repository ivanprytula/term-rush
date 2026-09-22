"""SQLAlchemy ORM models and session factory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import sessionmaker

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class GameRoundModel(Base):
    """GameRound entity in the database (stored as JSON for flexibility).

    Column length: worst case is ROUND_MAX_ANSWERS answers at max field
    lengths, ~37KB serialized; 65536 leaves headroom without another migration.
    """

    __tablename__ = "game_rounds"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[str] = mapped_column(String(65536), nullable=False)
    # Denormalized from data (SubmittedAnswer.score sum) so the leaderboard
    # can sort in SQL instead of deserializing every row's JSON in Python.
    total_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, index=True
    )
    # Denormalized from data (GameRound.mode) so the leaderboard can filter
    # in SQL instead of deserializing every row's JSON in Python.
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="classic")


class TermStatsModel(Base):
    """Verdict tally for one term (ADR-0011: the AnswerGraded consumer).

    Columnar, not a JSON blob like GameRoundModel: three counters keyed by
    term_id is genuinely tabular, no leaderboard-style sort to denormalize for.
    """

    __tablename__ = "term_stats"

    term_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    partial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def create_db_engine(database_url: str) -> tuple[Any, Any]:
    """Create async engine and session factory.

    Returns: (engine, session_factory) tuple.
    """
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    session_factory = sessionmaker(  # type: ignore
        engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory
