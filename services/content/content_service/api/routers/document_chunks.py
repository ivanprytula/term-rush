"""Document chunk endpoints: the RAG/analytics corpus (ADR-0018 Slice 1).

No review gate here, unlike review_queue.py — chunks are raw ingested text,
not LLM-authored knowledge published to players.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from fastapi import Depends
from fastapi import Query
from fastapi import status

from content_service.api.dependencies import get_unit_of_work
from content_service.api.schemas import DocumentChunkListResponse
from content_service.api.schemas import DocumentChunkResponse
from content_service.api.schemas import ErrorResponse
from content_service.api.schemas import IngestDocumentChunksRequest
from content_service.application.ports import UnitOfWork
from content_service.application.use_cases import IngestDocumentChunks
from content_service.application.use_cases import ListDocumentChunksBySource
from content_service.domain import constants

router = APIRouter(prefix="/document-chunks", tags=["document-chunks"])

SourceFileQuery = Annotated[
    str, Query(max_length=constants.DOCUMENT_CHUNK_SOURCE_FILE_MAX_LEN)
]


@router.post(
    "",
    response_model=DocumentChunkListResponse,
    status_code=status.HTTP_201_CREATED,
    responses={422: {"model": ErrorResponse}},
)
async def ingest_chunks(
    request: IngestDocumentChunksRequest,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> DocumentChunkListResponse:
    """Persist a batch of chunked document text."""
    use_case = IngestDocumentChunks(uow)
    chunks = await use_case.execute(tuple(c.to_chunk() for c in request.chunks))
    return DocumentChunkListResponse(
        chunks=tuple(DocumentChunkResponse.from_chunk(c) for c in chunks)
    )


@router.get(
    "",
    response_model=DocumentChunkListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_chunks_by_source(
    source_file: SourceFileQuery,
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> DocumentChunkListResponse:
    """List every chunk ingested from one source document, in order."""
    use_case = ListDocumentChunksBySource(uow)
    chunks = await use_case.execute(source_file)
    return DocumentChunkListResponse(
        chunks=tuple(DocumentChunkResponse.from_chunk(c) for c in chunks)
    )
