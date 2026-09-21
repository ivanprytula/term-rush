"""SQLAlchemy-backed repository implementations."""

from __future__ import annotations

import json

from sqlalchemy import bindparam
from sqlalchemy import cast
from sqlalchemy import column
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import true
from sqlalchemy.dialects.postgresql import JSONB
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

    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
    ) -> Term | None:
        """Fetch a random term, avoiding excluded_ids where possible, scoped
        to category if given.

        category filters via jsonb containment on the existing data column
        (no schema migration) — correct at today's corpus size (~10^3
        terms, ADR-0012); a GIN index on data::jsonb is the move if this
        query ever shows up in EXPLAIN ANALYZE as a real bottleneck.

        Falls back to the full matching set once excluded_ids covers every
        matching term (a round that has shown everything in its category
        should repeat, not fail).
        """
        stmt = select(TermModel).order_by(func.random()).limit(1)
        if category is not None:
            # bindparam(type_=JSONB), not cast(json.dumps(...), JSONB): the
            # latter binds the dumped string through the driver's varchar
            # encoder first, so Postgres receives a JSON string *containing*
            # JSON text rather than the object itself — @> then never matches.
            stmt = stmt.where(
                cast(TermModel.data, JSONB).op("@>")(
                    bindparam(
                        "category_filter",
                        {"categories": [{"slug": category}]},
                        type_=JSONB,
                    )
                )
            )
        if excluded_ids:
            stmt = stmt.where(TermModel.id.not_in(excluded_ids))
        result = await self.session.execute(stmt)
        model = result.scalars().first()
        if not model and excluded_ids:
            return await self.random(category=category)
        if not model:
            return None
        assert isinstance(model.data, str)
        data = json.loads(model.data)
        return Term(**data)

    async def categories(self) -> tuple[str, ...]:
        """List every category slug present in the term bank.

        jsonb_array_elements unnests each term's categories array so we can
        select distinct slugs in SQL rather than deserializing every row.
        Explicit JOIN ... ON true (a Postgres lateral join, since the
        function body references terms.data) rather than a comma-join in
        the FROM clause — same query, but doesn't trip SQLAlchemy's
        cartesian-product warning.
        """
        categories_elem = func.jsonb_array_elements(
            cast(TermModel.data, JSONB)["categories"]
        ).table_valued(column("value", JSONB), joins_implicitly=True)
        stmt = (
            select(func.distinct(categories_elem.c.value["slug"].astext))
            .select_from(TermModel)
            .join(categories_elem, true())
        )
        result = await self.session.execute(stmt)
        return tuple(sorted(result.scalars().all()))

    async def upsert(self, term: Term) -> None:
        """Create the term, or replace it if the ID already exists."""
        stmt = insert(TermModel).values(id=term.id, data=term.model_dump_json())
        stmt = stmt.on_conflict_do_update(
            index_elements=["id"], set_={"data": stmt.excluded.data}
        )
        await self.session.execute(stmt)
