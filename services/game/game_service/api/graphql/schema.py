"""The sessionScreen query: aggregates the session screen's three REST
reads (GET /game-config, /terms/categories, /terms/random) into one round
trip. See ADR-0010. No domain logic here — every field calls the same use
cases/constants the REST routers already call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import strawberry
from fastapi import Depends
from strawberry.fastapi import BaseContext
from strawberry.fastapi import GraphQLRouter

from game_service.api.dependencies import get_unit_of_work
from game_service.api.graphql.types import GameConfig
from game_service.api.graphql.types import SessionScreen
from game_service.api.graphql.types import TermPrompt
from game_service.api.routers.config import build_game_config
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetNextTerm
from game_service.application.use_cases import ListTermCategories

logger = logging.getLogger(__name__)


@dataclass
class Context(BaseContext):
    uow: UnitOfWork


async def get_context(uow: UnitOfWork = Depends(get_unit_of_work)) -> Context:
    """Resolve the request's UnitOfWork through the same FastAPI Depends()
    graph the REST routers use, so app.dependency_overrides (tests) and
    lifespan-managed state (production) both apply here identically."""
    return Context(uow=uow)


@strawberry.type
class Query:
    @strawberry.field
    async def session_screen(
        self, info: strawberry.Info[Context], category: str | None = None
    ) -> SessionScreen:
        """Aggregate gameConfig, termCategories, and randomTerm for the
        session screen's initial load.

        randomTerm is null (not a query-level error) when no term matches
        — an empty bank or an empty category is a real, displayable state,
        not a failure of the other two fields.
        """
        uow = info.context.uow
        categories = await ListTermCategories(uow).execute()
        try:
            term = await GetNextTerm(uow).execute(category=category)
            random_term = TermPrompt.from_term(term)
        except ValueError as exc:
            logger.warning(f"sessionScreen randomTerm lookup failed: {exc}")
            random_term = None

        return SessionScreen(
            game_config=GameConfig.from_response(build_game_config()),
            term_categories=list(categories),
            random_term=random_term,
        )


schema = strawberry.Schema(query=Query)
graphql_router = GraphQLRouter(schema, context_getter=get_context)
