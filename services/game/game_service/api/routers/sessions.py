"""Session lookup endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from game_service.api.dependencies import get_unit_of_work
from game_service.api.schemas import ErrorResponse
from game_service.api.schemas import SessionIdPath
from game_service.api.schemas import SessionResponse
from game_service.application.ports import UnitOfWork
from game_service.application.use_cases import GetSession

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get(
    "/{session_id}",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_session(
    session_id: SessionIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> SessionResponse:
    """Fetch a session's recorded answer history."""
    use_case = GetSession(uow)
    try:
        session = await use_case.execute(session_id)
        return SessionResponse.from_session(session)
    except ValueError as exc:
        logger.warning(f"Session lookup failed: {exc}")
        raise exc
