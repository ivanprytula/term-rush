"""SQLAlchemy ORM models and session factory."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from sqlalchemy.orm import sessionmaker

from content_service.domain import constants

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
    """A term's scalar fields. Child tables hold its list fields (one row
    per list entry) — see TermDefinitionModel and siblings below.
    """

    __tablename__ = "terms"

    id: Mapped[str] = mapped_column(String(constants.TERM_ID_MAX_LEN), primary_key=True)
    term: Mapped[str] = mapped_column(String(constants.TERM_MAX_LEN), nullable=False)
    expansion: Mapped[str] = mapped_column(
        String(constants.TERM_EXPANSION_MAX_LEN), nullable=False
    )
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)

    definitions: Mapped[list[TermDefinitionModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermDefinitionModel.position",
    )
    aliases: Mapped[list[TermAliasModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermAliasModel.position",
    )
    examples: Mapped[list[TermExampleModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermExampleModel.position",
    )
    categories: Mapped[list[TermCategoryModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermCategoryModel.position",
    )
    prerequisites: Mapped[list[TermPrerequisiteModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermPrerequisiteModel.position",
        foreign_keys="TermPrerequisiteModel.term_id",
    )
    related: Mapped[list[TermRelatedModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermRelatedModel.position",
        foreign_keys="TermRelatedModel.term_id",
    )
    common_mistakes: Mapped[list[TermCommonMistakeModel]] = relationship(
        back_populates="term_row",
        cascade="all, delete-orphan",
        order_by="TermCommonMistakeModel.position",
    )


class _TermChildMixin:
    """Shared shape for a term's list-field child tables: a term_id FK, a
    position to preserve list order (SQL has no ordered array type here),
    and the text value itself.
    """

    term_id: Mapped[str] = mapped_column(
        ForeignKey("terms.id", ondelete="CASCADE"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)


class TermDefinitionModel(_TermChildMixin, Base):
    __tablename__ = "term_definitions"

    value: Mapped[str] = mapped_column(
        String(constants.TERM_DEFINITION_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(back_populates="definitions")


class TermAliasModel(_TermChildMixin, Base):
    __tablename__ = "term_aliases"

    value: Mapped[str] = mapped_column(String(constants.TERM_MAX_LEN), nullable=False)

    term_row: Mapped[TermModel] = relationship(back_populates="aliases")


class TermExampleModel(_TermChildMixin, Base):
    __tablename__ = "term_examples"

    value: Mapped[str] = mapped_column(
        String(constants.TERM_DEFINITION_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(back_populates="examples")


class TermCategoryModel(_TermChildMixin, Base):
    __tablename__ = "term_categories"

    slug: Mapped[str] = mapped_column(
        String(constants.TERM_SLUG_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(back_populates="categories")

    __table_args__ = (
        UniqueConstraint("term_id", "slug", name="uq_term_categories_term_id_slug"),
    )


class TermPrerequisiteModel(_TermChildMixin, Base):
    """A term's prerequisites, self-referential to terms.id. No FK
    constraint on requires_term_id: prerequisites may be authored before
    every referenced term exists (ADR-0004, content mined incrementally).
    """

    __tablename__ = "term_prerequisites"

    requires_term_id: Mapped[str] = mapped_column(
        String(constants.TERM_ID_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(
        back_populates="prerequisites", foreign_keys="TermPrerequisiteModel.term_id"
    )


class TermRelatedModel(_TermChildMixin, Base):
    """A term's related-term links, self-referential to terms.id. Same
    no-FK-constraint reasoning as TermPrerequisiteModel.
    """

    __tablename__ = "term_related"

    related_term_id: Mapped[str] = mapped_column(
        String(constants.TERM_ID_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(
        back_populates="related", foreign_keys="TermRelatedModel.term_id"
    )


class TermCommonMistakeModel(_TermChildMixin, Base):
    __tablename__ = "term_common_mistakes"

    value: Mapped[str] = mapped_column(
        String(constants.TERM_DEFINITION_MAX_LEN), nullable=False
    )

    term_row: Mapped[TermModel] = relationship(back_populates="common_mistakes")


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
