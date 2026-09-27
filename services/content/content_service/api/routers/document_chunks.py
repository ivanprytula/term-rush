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

from content_service.api.dependencies import get_embedder
from content_service.api.dependencies import get_unit_of_work
from content_service.api.schemas import DocumentChunkListResponse
from content_service.api.schemas import DocumentChunkResponse
from content_service.api.schemas import EmbedDocumentChunksResponse
from content_service.api.schemas import ErrorResponse
from content_service.api.schemas import IngestDocumentChunksRequest
from content_service.application.ports import UnitOfWork
from content_service.application.use_cases import EmbedDocumentChunks
from content_service.application.use_cases import IngestDocumentChunks
from content_service.application.use_cases import ListDocumentChunksBySource
from content_service.application.use_cases import SearchChunksBySimilarity
from content_service.domain import constants
from content_service.domain.embedding import EmbeddingPort

router = APIRouter(prefix="/document-chunks", tags=["document-chunks"])

SourceFileQuery = Annotated[
    str, Query(max_length=constants.DOCUMENT_CHUNK_SOURCE_FILE_MAX_LEN)
]
SearchQuery = Annotated[
    str, Query(min_length=1, max_length=constants.DOCUMENT_CHUNK_MAX_LEN)
]
TopKQuery = Annotated[int, Query(ge=1, le=100)]


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


@router.post(
    "/embed",
    response_model=EmbedDocumentChunksResponse,
    status_code=status.HTTP_200_OK,
)
async def embed_pending_chunks(
    uow: UnitOfWork = Depends(get_unit_of_work),
    embedder: EmbeddingPort = Depends(get_embedder),
) -> EmbedDocumentChunksResponse:
    """Embed one bounded batch of not-yet-embedded chunks (ADR-0012 Slice
    2). Call repeatedly (poll, or a scheduled job) until embedded_count is
    0 — each call only advances the backlog by one batch, it doesn't drain
    it."""
    use_case = EmbedDocumentChunks(uow, embedder)
    chunks = await use_case.execute()
    return EmbedDocumentChunksResponse.from_chunks(chunks)


@router.get(
    "/search",
    response_model=DocumentChunkListResponse,
    status_code=status.HTTP_200_OK,
    operation_id="search_document_chunks",
)
async def search_chunks(
    query: SearchQuery,
    top_k: TopKQuery = constants.SEARCH_DEFAULT_TOP_K,
    uow: UnitOfWork = Depends(get_unit_of_work),
    embedder: EmbeddingPort = Depends(get_embedder),
) -> DocumentChunkListResponse:
    """Semantic search over embedded chunks (ADR-0012 Slice 2): the RAG
    retrieval step. Chunks with no embedding yet aren't candidates — see
    POST /document-chunks/embed. top_k is capped at 100 as a sanity bound
    at the API boundary, not a tuned retrieval-quality limit."""
    use_case = SearchChunksBySimilarity(uow, embedder)
    chunks = await use_case.execute(query, top_k)
    return DocumentChunkListResponse(
        chunks=tuple(DocumentChunkResponse.from_chunk(c) for c in chunks)
    )
