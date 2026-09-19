"""Answer submission endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from api.dependencies import get_unit_of_work
from api.schemas import ErrorResponse
from api.schemas import SessionIdPath
from api.schemas import SubmitAnswerRequest
from api.schemas import SubmitAnswerResponse
from application.ports import UnitOfWork
from application.use_cases import SubmitAnswer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["answers"])


@router.post(
    "/{session_id}/answers/submit",
    response_model=SubmitAnswerResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def submit_answer(
    session_id: SessionIdPath,
    payload: SubmitAnswerRequest,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> SubmitAnswerResponse:
    """Submit an answer for grading.

    Returns the grade outcome with rubric breakdown and feedback. The answer
    is recorded against the session; identical answers are cached, and
    grading is deterministic in Phase 1.
    """
    use_case = SubmitAnswer(uow)
    try:
        outcome = await use_case.execute(session_id, payload.term_id, payload.answer)
        return SubmitAnswerResponse.from_outcome(outcome)
    except ValueError as exc:
        logger.warning(f"Grading failed: {exc}")
        raise exc
