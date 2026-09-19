"""Answer submission endpoints."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status
from sse_starlette.sse import EventSourceResponse

from api.dependencies import get_answer_evaluator
from api.dependencies import get_llm_grader
from api.dependencies import get_unit_of_work
from api.schemas import ErrorResponse
from api.schemas import SessionIdPath
from api.schemas import SubmitAnswerRequest
from api.schemas import SubmitAnswerResponse
from api.schemas import SubmitAnswerStreamEvent
from application.ports import UnitOfWork
from application.use_cases import SubmitAnswer
from application.use_cases import SubmitAnswerStreaming
from domain.graders import AnswerEvaluator
from domain.llm_grader import LLMRubricGrader

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
    evaluator: AnswerEvaluator = Depends(get_answer_evaluator),
    llm_grader: LLMRubricGrader | None = Depends(get_llm_grader),
) -> SubmitAnswerResponse:
    """Submit an answer for grading.

    Returns the grade outcome with rubric breakdown and feedback. The answer
    is recorded against the session; identical answers are cached. Offensive
    answers are rejected before any correctness check runs. Grading is
    deterministic by default; PARTIAL verdicts additionally escalate to the
    LLM rubric judge when use_llm_grading is set and the server has one
    configured.
    """
    use_case = SubmitAnswer(uow, evaluator=evaluator, llm_grader=llm_grader)
    try:
        outcome = await use_case.execute(
            session_id, payload.term_id, payload.answer, payload.use_llm_grading
        )
        return SubmitAnswerResponse.from_outcome(outcome)
    except ValueError as exc:
        logger.warning(f"Grading failed: {exc}")
        raise exc


@router.post(
    "/{session_id}/answers/submit/stream",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def submit_answer_stream(
    session_id: SessionIdPath,
    payload: SubmitAnswerRequest,
    uow: UnitOfWork = Depends(get_unit_of_work),
    evaluator: AnswerEvaluator = Depends(get_answer_evaluator),
    llm_grader: LLMRubricGrader | None = Depends(get_llm_grader),
) -> EventSourceResponse:
    """Submit an answer for grading, streaming live LLM feedback via SSE.

    Always responds with text/event-stream. When the deterministic verdict
    is PARTIAL and use_llm_grading is set (and the server has an LLM grader
    configured), emits "rationale_delta" events as the judge's feedback
    generates, then one final "graded" event. Otherwise — CORRECT,
    INCORRECT, no opt-in, or a cache hit — emits only the single "graded"
    event immediately: there is nothing to stream.

    404 (term not found) surfaces as an "error" SSE event, not an HTTP 404
    status: the response has already started streaming by the time grading
    can fail, so the status code is fixed at 200 once the connection opens.
    """
    use_case = SubmitAnswerStreaming(uow, evaluator=evaluator, llm_grader=llm_grader)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        try:
            async for event in use_case.execute(
                session_id, payload.term_id, payload.answer, payload.use_llm_grading
            ):
                sse_event = SubmitAnswerStreamEvent.from_stream_event(event)
                yield {"event": sse_event.event, "data": sse_event.data}
        except ValueError as exc:
            logger.warning(f"Streaming grading failed: {exc}")
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_generator())
