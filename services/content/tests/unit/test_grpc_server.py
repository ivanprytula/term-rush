"""TermServiceServicer tests: request/reply mapping for each RPC."""

from __future__ import annotations

import pytest
from term_proto import term_pb2

from content_service.api.grpc.server import TermServiceServicer
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryUnitOfWork


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )


def _servicer(uow: InMemoryUnitOfWork) -> TermServiceServicer:
    async def get_unit_of_work():
        yield uow

    return TermServiceServicer(get_unit_of_work)


@pytest.mark.asyncio
async def test_get_random_without_category_returns_any_term(term: Term) -> None:
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term}))

    reply = await servicer.GetRandom(term_pb2.GetRandomRequest(), context=None)  # type: ignore

    assert reply.found
    assert reply.id == "uow"


@pytest.mark.asyncio
async def test_get_random_forwards_category_filter(term: Term) -> None:
    lambda_term = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    servicer = _servicer(
        InMemoryUnitOfWork(terms={term.id: term, lambda_term.id: lambda_term})
    )

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(category="python-keywords"),
        context=None,  # type: ignore
    )

    assert reply.found
    assert reply.id == "lambda"


@pytest.mark.asyncio
async def test_get_random_not_found_when_category_has_no_terms(term: Term) -> None:
    servicer = _servicer(InMemoryUnitOfWork(terms={term.id: term}))

    reply = await servicer.GetRandom(
        term_pb2.GetRandomRequest(category="nonexistent-category"),
        context=None,  # type: ignore
    )

    assert not reply.found


@pytest.mark.asyncio
async def test_list_categories_returns_every_distinct_slug(term: Term) -> None:
    lambda_term = term.model_copy(
        update={"id": "lambda", "categories": (Category(slug="python-keywords"),)}
    )
    servicer = _servicer(
        InMemoryUnitOfWork(terms={term.id: term, lambda_term.id: lambda_term})
    )

    reply = await servicer.ListCategories(
        term_pb2.ListCategoriesRequest(),
        context=None,  # type: ignore
    )

    assert tuple(reply.categories) == ("architecture", "python-keywords")
