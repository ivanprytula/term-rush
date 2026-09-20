"""Term lookup and authoring endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Path
from fastapi import status

from content_service.api.dependencies import get_unit_of_work
from content_service.api.schemas import ErrorResponse
from content_service.api.schemas import PublishTermRequest
from content_service.api.schemas import TermResponse
from content_service.application.ports import UnitOfWork
from content_service.application.use_cases import GetRandomTerm
from content_service.application.use_cases import GetTermById
from content_service.application.use_cases import PublishTerm
from content_service.domain import constants

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/terms", tags=["terms"])

TermIdPath = Annotated[str, Path(min_length=1, max_length=constants.TERM_ID_MAX_LEN)]


@router.get(
    "/random",
    response_model=TermResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_random_term(
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermResponse:
    """Fetch a random term."""
    use_case = GetRandomTerm(uow)
    try:
        term = await use_case.execute()
        return TermResponse.from_term(term)
    except ValueError as exc:
        logger.warning(f"Random term lookup failed: {exc}")
        raise exc


@router.get(
    "/{term_id}",
    response_model=TermResponse,
    status_code=status.HTTP_200_OK,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_term_by_id(
    term_id: TermIdPath,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermResponse:
    """Fetch a term by ID."""
    use_case = GetTermById(uow)
    try:
        term = await use_case.execute(term_id)
        return TermResponse.from_term(term)
    except ValueError as exc:
        logger.warning(f"Term lookup failed: {exc}")
        raise exc


@router.post(
    "",
    response_model=TermResponse,
    status_code=status.HTTP_200_OK,
    responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def publish_term(
    request: PublishTermRequest,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TermResponse:
    """Create a term, or replace it if the ID already exists."""
    use_case = PublishTerm(uow)
    term = await use_case.execute(request.to_term())
    return TermResponse.from_term(term)
