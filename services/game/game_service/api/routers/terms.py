"""Term lookup endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from game_service.api.dependencies import get_term_stats_repository
from game_service.api.dependencies import get_unit_of_work
from game_service.api.schemas import CategoryQuery
from game_service.api.schemas import ErrorResponse
from game_service.api.schemas import RoundIdQuery
from game_service.api.schemas import TermCategoriesResponse
from game_service.api.schemas import TermIdPath
from game_service.api.schemas import TermPromptResponse
from game_service.api.schemas import TermStatsResponse
from game_service.application.ports import TermStatsRepository
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetRandomTerm
from game_service.application.use_cases import ListTermCategories

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terms", tags=["terms"])


@router.get(
    "/random",
    response_model=TermPromptResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_random_term(
    round_id: RoundIdQuery = None,
    category: CategoryQuery = None,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermPromptResponse:
    """Fetch a random term to present to the player.

    round_id, if given, excludes terms already answered this round —
    avoids repeating a term mid-round where the bank allows it. category,
    if given, scopes the pick to a player-chosen collection (a category
    slug from GET /terms/categories).
    """
    use_case = GetRandomTerm(uow)
    try:
        term = await use_case.execute(round_id, category)
        return TermPromptResponse.from_term(term)
    except ValueError as exc:
        logger.warning(f"Random term lookup failed: {exc}")
        raise exc


@router.get(
    "/categories",
    response_model=TermCategoriesResponse,
    status_code=status.HTTP_200_OK,
)
async def get_term_categories(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermCategoriesResponse:
    """List every collection a player can choose to play from."""
    use_case = ListTermCategories(uow)
    categories = await use_case.execute()
    return TermCategoriesResponse(categories=categories)


@router.get(
    "/{term_id}/stats",
    response_model=TermStatsResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}},
)
async def get_term_stats(
    term_id: TermIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
    stats_repository: TermStatsRepository = Depends(get_term_stats_repository),
) -> TermStatsResponse:
    """Fetch observed difficulty for a term (ADR-0011: the AnswerGraded
    consumer's read side). 404 if the term itself doesn't exist; a real
    term with no graded answers yet returns zeros and a null
    observed_difficulty, not a 404 — those are different facts.
    """
    if await uow.terms.by_id(term_id) is None:
        raise ValueError(f"Term not found: {term_id}")
    stats = await stats_repository.get(term_id)
    if stats is None:
        return TermStatsResponse.empty(term_id)
    return TermStatsResponse.from_stats(stats)
