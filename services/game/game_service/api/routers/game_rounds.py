"""Game round lookup endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from game_service.api.dependencies import get_unit_of_work
from game_service.api.schemas import ErrorResponse
from game_service.api.schemas import RoundIdPath
from game_service.api.schemas import RoundResponse
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetRound

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/game-rounds", tags=["game-rounds"])


@router.get(
    "/{round_id}",
    response_model=RoundResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_round(
    round_id: RoundIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> RoundResponse:
    """Fetch a round's recorded answer history."""
    use_case = GetRound(uow)
    try:
        round_ = await use_case.execute(round_id)
        return RoundResponse.from_round(round_)
    except ValueError as exc:
        logger.warning(f"Round lookup failed: {exc}")
        raise exc
