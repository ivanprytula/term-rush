"""gRPC-backed TermRepository: term.py's promise made real.

Term's docstring has always said "terms are replaced by content-service
publishing a new version, never mutated in place by the game" — this is the
adapter that makes that literally true: game-service no longer owns a terms
table, it asks content-service over the network (ADR-0009).
"""

from __future__ import annotations

import logging
import time

import grpc
from term_proto import term_pb2
from term_proto import term_pb2_grpc

from game_service.application.ports import TermRepository
from game_service.domain.term import Category
from game_service.domain.term import Difficulty
from game_service.domain.term import Term
from game_service.domain.term import TermFilter

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # how stale a term may be before Kafka invalidation lands


def _from_reply(reply: term_pb2.TermReply) -> Term:
    return Term(
        id=reply.id,
        term=reply.term,
        expansion=reply.expansion,
        definitions=tuple(reply.definitions),
        aliases=tuple(reply.aliases),
        categories=tuple(Category(slug=c) for c in reply.categories),
        difficulty=Difficulty(reply.difficulty),
        examples=tuple(reply.examples),
        related=tuple(reply.related),
        prerequisites=tuple(reply.prerequisites),
        common_mistakes=tuple(reply.common_mistakes),
    )


class GrpcTermRepository(TermRepository):
    """Fetch term knowledge from content-service over gRPC.

    by_id is cached (grading looks up the same term_id repeatedly within a
    session); random is never cached — caching it would defeat the point.
    On an RPC failure, by_id falls back to a stale cache entry rather than
    failing the answer outright; random has no fallback, since content-
    service being down means there is genuinely no term to serve.
    """

    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = term_pb2_grpc.TermServiceStub(channel)
        self._cache: dict[str, tuple[Term, float]] = {}

    def invalidate(self, term_id: str) -> None:
        """Evict a cached term (called on a TermPublished event)."""
        self._cache.pop(term_id, None)

    async def by_id(self, term_id: str) -> Term | None:
        cached = self._cache.get(term_id)
        if cached is not None and time.monotonic() - cached[1] < CACHE_TTL_SECONDS:
            return cached[0]

        try:
            reply = await self._stub.GetById(term_pb2.GetByIdRequest(term_id=term_id))
        except grpc.aio.AioRpcError as exc:
            logger.warning("content-service GetById failed: %s", exc)
            return cached[0] if cached is not None else None

        if not reply.found:
            return None
        term = _from_reply(reply)
        self._cache[term_id] = (term, time.monotonic())
        return term

    async def random(
        self,
        excluded_ids: frozenset[str] = frozenset(),
        category: str | None = None,
        term_filter: TermFilter | None = None,
    ) -> Term | None:
        try:
            request = term_pb2.GetRandomRequest(
                excluded_ids=excluded_ids,
                category=category,
                min_difficulty=(
                    int(term_filter.min_difficulty)
                    if term_filter is not None
                    and term_filter.min_difficulty is not None
                    else None
                ),
                require_examples=(
                    term_filter.require_examples if term_filter is not None else None
                ),
                min_definition_length=(
                    term_filter.min_definition_length
                    if term_filter is not None
                    else None
                ),
            )
            reply = await self._stub.GetRandom(request)
        except grpc.aio.AioRpcError as exc:
            logger.warning("content-service GetRandom failed: %s", exc)
            return None

        if not reply.found:
            return None
        return _from_reply(reply)

    async def categories(self) -> tuple[str, ...]:
        try:
            reply = await self._stub.ListCategories(term_pb2.ListCategoriesRequest())
        except grpc.aio.AioRpcError as exc:
            logger.warning("content-service ListCategories failed: %s", exc)
            return ()
        return tuple(reply.categories)

    async def all_ids(self) -> tuple[str, ...]:
        try:
            reply = await self._stub.ListTermIds(term_pb2.ListTermIdsRequest())
        except grpc.aio.AioRpcError as exc:
            logger.warning("content-service ListTermIds failed: %s", exc)
            return ()
        return tuple(reply.term_ids)
