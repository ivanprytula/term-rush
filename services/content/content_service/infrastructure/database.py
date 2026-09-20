"""SQLAlchemy ORM models and session factory."""

from __future__ import annotations

from typing import Any

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


class TermModel(Base):
    """Term entity in the database (stored as JSON for flexibility)."""

    __tablename__ = "terms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[str] = mapped_column(String(4096), nullable=False)


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
