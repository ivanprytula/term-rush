"""FastAPI dependency injection."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from content_service.api.config import settings
from content_service.application.ports import UnitOfWork
from content_service.infrastructure.database import create_db_engine
from content_service.infrastructure.memory import InMemoryUnitOfWork
from content_service.infrastructure.sql_uow import SQLUnitOfWork

# Session factory and engine (created at app startup via lifespan)
_session_factory: Any = None
_engine: Any = None


async def _init_session_factory() -> None:
    """Initialize the session factory and engine (called from lifespan).

    No-ops when DATABASE_URL is unset: get_unit_of_work then falls back to
    the in-memory adapters, which is how tests run without a real database.
    """
    global _session_factory, _engine
    if settings.DATABASE_URL is None:
        return
    _engine, _session_factory = await create_db_engine(str(settings.DATABASE_URL))


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    """Provide a Unit of Work for the request (in-memory for tests, SQL for production).

    Manages session lifecycle: creates on entry, closes on exit.
    """
    if _session_factory is None:
        uow = InMemoryUnitOfWork()
        yield uow
    else:
        async with _session_factory() as session:
            yield SQLUnitOfWork(session)
