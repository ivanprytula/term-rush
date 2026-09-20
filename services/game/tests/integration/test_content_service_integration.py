"""Proves GrpcTermRepository against a real gRPC server, not a stub.

Exercises the actual term.proto wire contract end-to-end (server -> channel
-> GrpcTermRepository), which unit tests fake out. Does not import
content_service — that would couple game-service's tests to content-service's
internals, which is exactly what the isolation contract exists to prevent.
This servicer is a minimal stand-in that speaks the same proto.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import grpc
import pytest
from term_proto import term_pb2
from term_proto import term_pb2_grpc

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository


class _TermServiceServicer(term_pb2_grpc.TermServiceServicer):
    """Minimal server-side stand-in for content-service's own servicer."""

    def __init__(self, terms: dict[str, term_pb2.TermReply]) -> None:
        self._terms = terms

    async def GetById(
        self, request: term_pb2.GetByIdRequest, context: grpc.aio.ServicerContext
    ) -> term_pb2.TermReply:
        return self._terms.get(request.term_id, term_pb2.TermReply(found=False))

    async def GetRandom(
        self, request: term_pb2.GetRandomRequest, context: grpc.aio.ServicerContext
    ) -> term_pb2.TermReply:
        if not self._terms:
            return term_pb2.TermReply(found=False)
        return next(iter(self._terms.values()))


@pytest.fixture
async def grpc_repository() -> AsyncIterator[GrpcTermRepository]:
    """A GrpcTermRepository talking to a real, in-process gRPC server."""
    reply = term_pb2.TermReply(
        found=True,
        id="outbox-pattern",
        term="Outbox Pattern",
        expansion="Transactional Outbox Pattern",
        definitions=["Writes an event and its state change in one transaction."],
        categories=["distributed-systems"],
        difficulty=3,
    )
    server = grpc.aio.server()
    term_pb2_grpc.add_TermServiceServicer_to_server(
        _TermServiceServicer({"outbox-pattern": reply}), server
    )
    port = server.add_insecure_port("[::]:0")
    await server.start()
    channel = grpc.aio.insecure_channel(f"localhost:{port}")
    try:
        yield GrpcTermRepository(channel)
    finally:
        await channel.close()
        await server.stop(grace=None)


@pytest.mark.asyncio
async def test_by_id_fetches_the_term_over_the_wire(
    grpc_repository: GrpcTermRepository,
) -> None:
    """The literal "done" bar: a term reaches game-service over the network,
    not an import — game-service has no local copy of this term anywhere.
    """
    term = await grpc_repository.by_id("outbox-pattern")

    assert term is not None
    assert term.id == "outbox-pattern"
    assert term.expansion == "Transactional Outbox Pattern"


@pytest.mark.asyncio
async def test_by_id_returns_none_for_an_unknown_term(
    grpc_repository: GrpcTermRepository,
) -> None:
    assert await grpc_repository.by_id("nonexistent") is None


@pytest.mark.asyncio
async def test_random_fetches_a_term_over_the_wire(
    grpc_repository: GrpcTermRepository,
) -> None:
    term = await grpc_repository.random()

    assert term is not None
    assert term.id == "outbox-pattern"
