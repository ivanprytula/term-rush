"""Term lookup endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from api.dependencies import get_unit_of_work
from api.schemas import ErrorResponse
from api.schemas import TermPromptResponse
from application.ports import UnitOfWork
from application.use_cases import GetRandomTerm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terms", tags=["terms"])


@router.get(
    "/random",
    response_model=TermPromptResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_random_term(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermPromptResponse:
    """Fetch a random term to present to the player."""
    use_case = GetRandomTerm(uow)
    try:
        term = await use_case.execute()
        return TermPromptResponse.from_term(term)
    except ValueError as exc:
        logger.warning(f"Random term lookup failed: {exc}")
        raise exc
