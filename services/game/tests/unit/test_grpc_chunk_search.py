"""GrpcChunkSearch tests: reply mapping, failure returns empty."""

from __future__ import annotations

import grpc
import pytest
from term_proto import term_pb2

from game_service.infrastructure.grpc_chunk_search import GrpcChunkSearch


class _FakeStub:
    """Replaces term_pb2_grpc.TermServiceStub: one canned reply or error."""

    def __init__(self) -> None:
        self.search_chunks_reply: term_pb2.SearchChunksReply | None = None
        self.search_chunks_error: Exception | None = None
        self.last_request: term_pb2.SearchChunksRequest | None = None

    async def SearchChunks(
        self, request: term_pb2.SearchChunksRequest
    ) -> term_pb2.SearchChunksReply:
        self.last_request = request
        if self.search_chunks_error is not None:
            raise self.search_chunks_error
        assert self.search_chunks_reply is not None
        return self.search_chunks_reply


def _chunk_search() -> tuple[GrpcChunkSearch, _FakeStub]:
    search = GrpcChunkSearch.__new__(GrpcChunkSearch)
    stub = _FakeStub()
    search._stub = stub  # type: ignore
    return search, stub


@pytest.mark.asyncio
async def test_search_maps_chunks_from_the_reply() -> None:
    search, stub = _chunk_search()
    stub.search_chunks_reply = term_pb2.SearchChunksReply(
        chunks=[
            term_pb2.DocumentChunkResult(text="chunk one", source_file="a.txt"),
            term_pb2.DocumentChunkResult(text="chunk two", source_file="b.txt"),
        ]
    )

    results = await search.search("query", top_k=5)

    assert [r.text for r in results] == ["chunk one", "chunk two"]
    assert [r.source_file for r in results] == ["a.txt", "b.txt"]


@pytest.mark.asyncio
async def test_search_forwards_query_and_top_k() -> None:
    search, stub = _chunk_search()
    stub.search_chunks_reply = term_pb2.SearchChunksReply()

    await search.search("gradient descent", top_k=3)

    assert stub.last_request is not None
    assert stub.last_request.query == "gradient descent"
    assert stub.last_request.top_k == 3


@pytest.mark.asyncio
async def test_search_returns_empty_on_rpc_failure() -> None:
    search, stub = _chunk_search()
    stub.search_chunks_error = grpc.aio.AioRpcError(code=grpc.StatusCode.UNAVAILABLE)

    results = await search.search("query", top_k=5)

    assert results == ()


@pytest.mark.asyncio
async def test_search_returns_empty_when_reply_has_no_chunks() -> None:
    search, stub = _chunk_search()
    stub.search_chunks_reply = term_pb2.SearchChunksReply()

    results = await search.search("query", top_k=5)

    assert results == ()
