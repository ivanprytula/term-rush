#!/usr/bin/env python3
"""Seed the terms table with sample data for local development."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy.dialects.postgresql import insert

from api.config import settings
from domain.term import Category
from domain.term import Difficulty
from domain.term import Term
from infrastructure.database import TermModel
from infrastructure.database import create_db_engine

logger = logging.getLogger(__name__)

SEED_TERMS = (
    Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        aliases=("Unit-of-Work",),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.HARD,
        examples=("Committing several repository writes as one transaction.",),
    ),
    Term(
        id="idempotent",
        term="Idempotent",
        expansion="Idempotency",
        definitions=(
            "An operation that produces the same result no matter how many "
            "times it is applied.",
        ),
        categories=(Category(slug="distributed-systems"),),
        difficulty=Difficulty.MODERATE,
        examples=("Retrying a PUT request is safe because it is idempotent.",),
    ),
    Term(
        id="cap-theorem",
        term="CAP Theorem",
        expansion="Consistency, Availability, Partition tolerance",
        definitions=(
            "A distributed system can guarantee at most two of consistency, "
            "availability, and partition tolerance at once.",
        ),
        aliases=("CAP",),
        categories=(Category(slug="distributed-systems"),),
        difficulty=Difficulty.EXPERT,
        examples=("Choosing AP over CP during a network partition.",),
    ),
)


async def seed() -> None:
    """Upsert SEED_TERMS into the terms table."""
    engine, session_factory = await create_db_engine(str(settings.DATABASE_URL))
    async with session_factory() as session, session.begin():
        for term in SEED_TERMS:
            stmt = insert(TermModel).values(id=term.id, data=term.model_dump_json())
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"], set_={"data": stmt.excluded.data}
            )
            await session.execute(stmt)
    await engine.dispose()
    logger.info("Seeded %d terms.", len(SEED_TERMS))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())
