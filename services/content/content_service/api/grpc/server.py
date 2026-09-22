"""gRPC server: the internal, schema-first hop game-service uses for term lookup.

REST (api/routers/terms.py) is content-service's own public-ish surface; this
is the high-frequency, latency-sensitive internal one (ADR-0009).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from collections.abc import Callable
from contextlib import asynccontextmanager

import grpc
from term_proto import term_pb2
from term_proto import term_pb2_grpc

from content_service.application.ports import UnitOfWork
from content_service.application.use_cases import GetRandomTerm
from content_service.application.use_cases import GetTermById
from content_service.application.use_cases import ListAllTermIds
from content_service.application.use_cases import ListCategories
from content_service.domain.term import Term

logger = logging.getLogger(__name__)

UnitOfWorkFactory = Callable[[], AsyncGenerator[UnitOfWork]]

# get_unit_of_work is a FastAPI-Depends-shaped generator (yield once, cleanup
# on the caller driving it past the yield). A bare anext() takes the yielded
# value but abandons the generator without resuming it, so the session's
# __aexit__ never runs deterministically — GC finalizes it later and can
# throw GeneratorExit into it mid-query, racing the session's own I/O.
# asynccontextmanager drives it to completion properly on exit.


def _to_reply(term: Term) -> term_pb2.TermReply:
    return term_pb2.TermReply(
        found=True,
        id=term.id,
        term=term.term,
        expansion=term.expansion,
        definitions=term.definitions,
        aliases=term.aliases,
        categories=[str(c) for c in term.categories],
        difficulty=int(term.difficulty),
        examples=term.examples,
        related=term.related,
        prerequisites=term.prerequisites,
        common_mistakes=term.common_mistakes,
    )


class TermServiceServicer(term_pb2_grpc.TermServiceServicer):
    """Implements the TermService contract from term.proto."""

    def __init__(self, get_unit_of_work: UnitOfWorkFactory) -> None:
        self._get_unit_of_work = get_unit_of_work

    async def GetById(
        self, request: term_pb2.GetByIdRequest, context: grpc.aio.ServicerContext
    ) -> term_pb2.TermReply:
        async with asynccontextmanager(self._get_unit_of_work)() as uow:
            use_case = GetTermById(uow)
            try:
                term = await use_case.execute(request.term_id)
            except ValueError:
                return term_pb2.TermReply(found=False)
            return _to_reply(term)

    async def GetRandom(
        self, request: term_pb2.GetRandomRequest, context: grpc.aio.ServicerContext
    ) -> term_pb2.TermReply:
        async with asynccontextmanager(self._get_unit_of_work)() as uow:
            use_case = GetRandomTerm(uow)
            category = request.category if request.HasField("category") else None
            min_difficulty = (
                request.min_difficulty if request.HasField("min_difficulty") else None
            )
            min_definition_length = (
                request.min_definition_length
                if request.HasField("min_definition_length")
                else None
            )
            try:
                term = await use_case.execute(
                    frozenset(request.excluded_ids),
                    category,
                    min_difficulty,
                    request.require_examples,
                    min_definition_length,
                )
            except ValueError:
                return term_pb2.TermReply(found=False)
            return _to_reply(term)

    async def ListCategories(
        self,
        request: term_pb2.ListCategoriesRequest,
        context: grpc.aio.ServicerContext,
    ) -> term_pb2.ListCategoriesReply:
        async with asynccontextmanager(self._get_unit_of_work)() as uow:
            use_case = ListCategories(uow)
            categories = await use_case.execute()
            return term_pb2.ListCategoriesReply(categories=categories)

    async def ListTermIds(
        self,
        request: term_pb2.ListTermIdsRequest,
        context: grpc.aio.ServicerContext,
    ) -> term_pb2.ListTermIdsReply:
        async with asynccontextmanager(self._get_unit_of_work)() as uow:
            use_case = ListAllTermIds(uow)
            term_ids = await use_case.execute()
            return term_pb2.ListTermIdsReply(term_ids=term_ids)


async def serve(
    get_unit_of_work: UnitOfWorkFactory, port: int = 50051
) -> grpc.aio.Server:
    """Start the gRPC server and return it (caller awaits server.wait_for_termination())."""
    server = grpc.aio.server()
    term_pb2_grpc.add_TermServiceServicer_to_server(
        TermServiceServicer(get_unit_of_work), server
    )
    server.add_insecure_port(f"[::]:{port}")
    await server.start()
    logger.info("gRPC server listening on port %d", port)
    return server
