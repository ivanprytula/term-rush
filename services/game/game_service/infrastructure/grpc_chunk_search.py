"""gRPC-backed ChunkSearchPort: RAG retrieval over content-service's
document-chunk corpus, same internal hop as term lookup (ADR-0009,
ADR-0012 Slice 2).
"""

from __future__ import annotations

import logging

import grpc
from term_proto import term_pb2
from term_proto import term_pb2_grpc

from game_service.domain.chunk_search import ChunkSearchPort
from game_service.domain.chunk_search import RetrievedChunk

logger = logging.getLogger(__name__)


class GrpcChunkSearch(ChunkSearchPort):
    """Fetch semantically relevant chunks from content-service over gRPC.

    Never raises: a failed lookup means grading proceeds without retrieval
    context, not that grading fails. Same reasoning GrpcTermRepository
    applies to its own RPC failures, just with no cache to fall back to —
    a query's relevant chunks aren't repeated the way a term_id lookup is.
    """

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = term_pb2_grpc.TermServiceStub(channel)

    async def search(self, query: str, top_k: int) -> tuple[RetrievedChunk, ...]:
        try:
            reply = await self._stub.SearchChunks(
                term_pb2.SearchChunksRequest(query=query, top_k=top_k)
            )
        except grpc.aio.AioRpcError as exc:
            logger.warning("content-service SearchChunks failed: %s", exc)
            return ()
        return tuple(
            RetrievedChunk(text=c.text, source_file=c.source_file) for c in reply.chunks
        )
