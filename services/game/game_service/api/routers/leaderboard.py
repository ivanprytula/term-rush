"""Leaderboard endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi import status

from game_service.api.dependencies import get_unit_of_work
from game_service.api.schemas import ErrorResponse
from game_service.api.schemas import LeaderboardEntryResponse
from game_service.api.schemas import LeaderboardLimitQuery
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetLeaderboard
from game_service.domain import constants
from game_service.domain.round import RoundMode

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get(
    "",
    response_model=list[LeaderboardEntryResponse],
    status_code=status.HTTP_200_OK,
    responses={500: {"model": ErrorResponse}},
)
async def get_leaderboard(
    limit: LeaderboardLimitQuery = constants.LEADERBOARD_DEFAULT_LIMIT,
    mode: RoundMode | None = Query(default=None),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> list[LeaderboardEntryResponse]:
    """Fetch the top rounds by total score, highest first.

    Scoped to `mode` when given; otherwise mixes every mode's scores."""
    use_case = GetLeaderboard(uow)
    rounds = await use_case.execute(limit, mode)
    return [LeaderboardEntryResponse.from_round(r) for r in rounds]
