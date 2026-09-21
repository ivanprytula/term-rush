"""GrpcTermRepository tests: cache, fallback, invalidation."""

from __future__ import annotations

import grpc
import pytest
from term_proto import term_pb2

from game_service.infrastructure.grpc_term_repository import GrpcTermRepository


class _FakeStub:
    """Replaces term_pb2_grpc.TermServiceStub: one canned reply or error per call."""

    def __init__(self) -> None:
        self.get_by_id_reply: term_pb2.TermReply | None = None
        self.get_by_id_error: Exception | None = None
        self.get_random_reply: term_pb2.TermReply | None = None
        self.get_random_error: Exception | None = None
        self.list_categories_reply: term_pb2.ListCategoriesReply | None = None
        self.list_categories_error: Exception | None = None
        self.calls: list[str] = []
        self.last_get_random_request: term_pb2.GetRandomRequest | None = None

    async def GetById(self, request: term_pb2.GetByIdRequest) -> term_pb2.TermReply:
        self.calls.append(f"GetById:{request.term_id}")
        if self.get_by_id_error is not None:
            raise self.get_by_id_error
        assert self.get_by_id_reply is not None
        return self.get_by_id_reply

    async def GetRandom(self, request: term_pb2.GetRandomRequest) -> term_pb2.TermReply:
        self.calls.append("GetRandom")
        self.last_get_random_request = request
        if self.get_random_error is not None:
            raise self.get_random_error
        assert self.get_random_reply is not None
        return self.get_random_reply

    async def ListCategories(
        self, request: term_pb2.ListCategoriesRequest
    ) -> term_pb2.ListCategoriesReply:
        self.calls.append("ListCategories")
        if self.list_categories_error is not None:
            raise self.list_categories_error
        assert self.list_categories_reply is not None
        return self.list_categories_reply


def _repository() -> tuple[GrpcTermRepository, _FakeStub]:
    repo = GrpcTermRepository.__new__(GrpcTermRepository)
    stub = _FakeStub()
    repo._stub = stub  # type: ignore
    repo._cache = {}
    return repo, stub


def _reply(term_id: str = "uow") -> term_pb2.TermReply:
    return term_pb2.TermReply(
        found=True,
        id=term_id,
        term="UoW",
        expansion="Unit of Work",
        definitions=["Pattern that groups related changes into one unit."],
        categories=["architecture"],
        difficulty=3,
    )


@pytest.mark.asyncio
async def test_by_id_returns_none_when_not_found() -> None:
    repo, stub = _repository()
    stub.get_by_id_reply = term_pb2.TermReply(found=False)

    assert await repo.by_id("missing") is None


@pytest.mark.asyncio
async def test_by_id_returns_the_term() -> None:
    repo, stub = _repository()
    stub.get_by_id_reply = _reply()

    term = await repo.by_id("uow")

    assert term is not None
    assert term.id == "uow"
    assert term.expansion == "Unit of Work"


@pytest.mark.asyncio
async def test_by_id_caches_and_skips_a_second_rpc() -> None:
    repo, stub = _repository()
    stub.get_by_id_reply = _reply()

    await repo.by_id("uow")
    await repo.by_id("uow")

    assert stub.calls == ["GetById:uow"]


@pytest.mark.asyncio
async def test_by_id_falls_back_to_stale_cache_on_rpc_failure() -> None:
    repo, stub = _repository()
    stub.get_by_id_reply = _reply()
    await repo.by_id("uow")  # populate cache

    stub.get_by_id_error = grpc.aio.AioRpcError(code=grpc.StatusCode.UNAVAILABLE)
    term = await repo.by_id("uow")

    assert term is not None
    assert term.id == "uow"


@pytest.mark.asyncio
async def test_by_id_returns_none_on_rpc_failure_with_empty_cache() -> None:
    repo, stub = _repository()
    stub.get_by_id_error = grpc.aio.AioRpcError(code=grpc.StatusCode.UNAVAILABLE)

    assert await repo.by_id("uow") is None


@pytest.mark.asyncio
async def test_invalidate_evicts_the_cached_term() -> None:
    repo, stub = _repository()
    stub.get_by_id_reply = _reply()
    await repo.by_id("uow")

    repo.invalidate("uow")
    await repo.by_id("uow")

    assert stub.calls == ["GetById:uow", "GetById:uow"]


@pytest.mark.asyncio
async def test_random_returns_the_term() -> None:
    repo, stub = _repository()
    stub.get_random_reply = _reply()

    term = await repo.random()

    assert term is not None
    assert term.id == "uow"


@pytest.mark.asyncio
async def test_random_returns_none_when_bank_is_empty() -> None:
    repo, stub = _repository()
    stub.get_random_reply = term_pb2.TermReply(found=False)

    assert await repo.random() is None


@pytest.mark.asyncio
async def test_random_returns_none_on_rpc_failure() -> None:
    repo, stub = _repository()
    stub.get_random_error = grpc.aio.AioRpcError(code=grpc.StatusCode.UNAVAILABLE)

    assert await repo.random() is None


@pytest.mark.asyncio
async def test_random_forwards_category_to_the_request() -> None:
    repo, stub = _repository()
    stub.get_random_reply = _reply()

    await repo.random(category="python-keywords")

    assert stub.last_get_random_request is not None
    assert stub.last_get_random_request.HasField("category")
    assert stub.last_get_random_request.category == "python-keywords"


@pytest.mark.asyncio
async def test_random_without_category_leaves_the_field_unset() -> None:
    repo, stub = _repository()
    stub.get_random_reply = _reply()

    await repo.random()

    assert stub.last_get_random_request is not None
    assert not stub.last_get_random_request.HasField("category")


@pytest.mark.asyncio
async def test_categories_returns_the_reply_slugs() -> None:
    repo, stub = _repository()
    stub.list_categories_reply = term_pb2.ListCategoriesReply(
        categories=["architecture", "python-keywords"]
    )

    result = await repo.categories()

    assert result == ("architecture", "python-keywords")


@pytest.mark.asyncio
async def test_categories_returns_empty_on_rpc_failure() -> None:
    repo, stub = _repository()
    stub.list_categories_error = grpc.aio.AioRpcError(code=grpc.StatusCode.UNAVAILABLE)

    assert await repo.categories() == ()
