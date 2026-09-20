"""Term lookup endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from game_service.api.dependencies import get_unit_of_work
from game_service.api.schemas import ErrorResponse
from game_service.api.schemas import SessionIdQuery
from game_service.api.schemas import TermPromptResponse
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetRandomTerm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terms", tags=["terms"])


@router.get(
    "/random",
    response_model=TermPromptResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_random_term(
    session_id: SessionIdQuery = None,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermPromptResponse:
    """Fetch a random term to present to the player.

    session_id, if given, excludes terms already answered this session —
    avoids repeating a term mid-round where the bank allows it.
    """
    use_case = GetRandomTerm(uow)
    try:
        term = await use_case.execute(session_id)
        return TermPromptResponse.from_term(term)
    except ValueError as exc:
        logger.warning(f"Random term lookup failed: {exc}")
        raise exc
