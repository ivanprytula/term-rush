"""Semantic search over content-service's RAG document-chunk corpus
(ADR-0012 Slice 2) — a thin pass-through so game-service's own clients can
query the corpus without calling content-service's REST API directly.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi import Depends
from fastapi import status

from game_service.api.dependencies import get_chunk_search
from game_service.api.schemas import ChunkSearchQuery
from game_service.api.schemas import ChunkSearchResponse
from game_service.api.schemas import ChunkSearchTopKQuery
from game_service.api.schemas import RetrievedChunkResponse
from game_service.application.use_cases import SearchDocumentChunks
from game_service.domain import constants
from game_service.domain.chunk_search import ChunkSearchPort

router = APIRouter(prefix="/document-chunks", tags=["document-chunks"])


@router.get(
    "/search",
    response_model=ChunkSearchResponse,
    status_code=status.HTTP_200_OK,
)
async def search_chunks(
    query: ChunkSearchQuery,
    top_k: ChunkSearchTopKQuery = constants.CHUNK_SEARCH_DEFAULT_TOP_K,
    chunk_search: ChunkSearchPort | None = Depends(get_chunk_search),
) -> ChunkSearchResponse:
    """Retrieval only, no LLM synthesis — the caller reads the raw ranked
    chunks. Returns an empty list (not an error) when content-service's
    gRPC channel isn't configured (the in-memory/test path) or when the
    RPC itself fails — ChunkSearchPort never raises."""
    if chunk_search is None:
        return ChunkSearchResponse(chunks=())
    use_case = SearchDocumentChunks(chunk_search)
    chunks = await use_case.execute(query, top_k)
    return ChunkSearchResponse(
        chunks=tuple(RetrievedChunkResponse.from_chunk(c) for c in chunks)
    )
