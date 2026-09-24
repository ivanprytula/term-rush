"""Review queue endpoints: pipeline submission and human approval."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Path
from fastapi import status

from content_service.api.dependencies import get_unit_of_work
from content_service.api.schemas import ErrorResponse
from content_service.api.schemas import ReviewCandidateConflictResponse
from content_service.api.schemas import ReviewCandidateResponse
from content_service.api.schemas import ReviewQueueListResponse
from content_service.api.schemas import ReviewStatusQuery
from content_service.api.schemas import SubmitReviewCandidateRequest
from content_service.api.schemas import TermResponse
from content_service.application.ports import UnitOfWork
from content_service.application.use_cases import ApproveReviewCandidate
from content_service.application.use_cases import ListReviewCandidates
from content_service.application.use_cases import RejectReviewCandidate
from content_service.application.use_cases import SubmitReviewCandidate
from content_service.domain.review import ReviewCandidateNotPending
from content_service.domain.review import ReviewStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review-queue", tags=["review-queue"])

CandidateIdPath = Annotated[int, Path(ge=1)]


@router.post(
    "/candidates",
    response_model=ReviewCandidateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
async def submit_candidate(
    request: SubmitReviewCandidateRequest,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ReviewCandidateResponse:
    """Queue a pipeline-enriched candidate for human review. Always lands
    pending — never auto-promoted, regardless of confidence."""
    use_case = SubmitReviewCandidate(uow)
    candidate = await use_case.execute(
        term=request.term.to_term(),
        source_type=request.source_type,
        source_file=request.source_file,
        confidence=request.confidence,
    )
    return ReviewCandidateResponse.from_candidate(candidate)


@router.get(
    "",
    response_model=ReviewQueueListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_candidates(
    review_status: ReviewStatusQuery = ReviewStatus.PENDING,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> ReviewQueueListResponse:
    """List review candidates by status (defaults to pending)."""
    use_case = ListReviewCandidates(uow)
    candidates = await use_case.execute(review_status)
    return ReviewQueueListResponse(
        candidates=tuple(ReviewCandidateResponse.from_candidate(c) for c in candidates)
    )


@router.post(
    "/{candidate_id}/approve",
    response_model=TermResponse,
    status_code=status.HTTP_200_OK,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ReviewCandidateConflictResponse},
    },
)
async def approve_candidate(
    candidate_id: CandidateIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermResponse:
    """Promote a pending candidate into the live term bank."""
    use_case = ApproveReviewCandidate(uow)
    try:
        term = await use_case.execute(candidate_id)
        return TermResponse.from_term(term)
    except (ValueError, ReviewCandidateNotPending) as exc:
        logger.warning(f"Review candidate approval failed: {exc}")
        raise exc


@router.post(
    "/{candidate_id}/reject",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ReviewCandidateConflictResponse},
    },
)
async def reject_candidate(
    candidate_id: CandidateIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> None:
    """Reject a pending candidate. It never reaches the live term bank."""
    use_case = RejectReviewCandidate(uow)
    try:
        await use_case.execute(candidate_id)
    except (ValueError, ReviewCandidateNotPending) as exc:
        logger.warning(f"Review candidate rejection failed: {exc}")
        raise exc
