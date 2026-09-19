#!/usr/bin/env python3
"""Seed the terms table with sample data for local development.

Content lives in seed_terms.json, not inline here, so it can later be
regenerated or extended by a fetch/ETL step instead of hand-edited Python.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert

from api.config import settings
from domain.term import Term
from infrastructure.database import TermModel
from infrastructure.database import create_db_engine

logger = logging.getLogger(__name__)

SEED_TERMS_PATH = Path(__file__).parent / "seed_terms.json"


def _load_seed_terms(path: Path = SEED_TERMS_PATH) -> tuple[Term, ...]:
    """Parse and validate seed_terms.json into Term domain objects.

    The file's `categories` are bare strings (terser to hand-author or
    generate); Term.categories needs Category objects, so that's the one
    shape transform on the way in.
    """
    raw: list[dict[str, Any]] = json.loads(path.read_text())
    terms = []
    for entry in raw:
        entry = {**entry, "categories": [{"slug": c} for c in entry["categories"]]}
        terms.append(Term.model_validate(entry))
    return tuple(terms)


SEED_TERMS = _load_seed_terms()


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
