"""Application use case tests."""

from __future__ import annotations

import pytest

from content_service.application.use_cases import GetRandomTerm
from content_service.application.use_cases import GetTermById
from content_service.application.use_cases import PublishTerm
from content_service.domain.term import Category
from content_service.domain.term import Term
from content_service.infrastructure.memory import InMemoryEventPublisher
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


@pytest.fixture
def uow(term: Term) -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork(terms={term.id: term})


@pytest.mark.asyncio
async def test_get_term_by_id_returns_the_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetTermById(uow)

    assert await use_case.execute(term.id) == term


@pytest.mark.asyncio
async def test_get_term_by_id_raises_when_missing(uow: InMemoryUnitOfWork) -> None:
    use_case = GetTermById(uow)

    with pytest.raises(ValueError, match="not found"):
        await use_case.execute("nonexistent")


@pytest.mark.asyncio
async def test_get_random_term_returns_the_only_term(
    uow: InMemoryUnitOfWork, term: Term
) -> None:
    use_case = GetRandomTerm(uow)

    assert await use_case.execute() == term


@pytest.mark.asyncio
async def test_get_random_term_raises_when_bank_is_empty() -> None:
    use_case = GetRandomTerm(InMemoryUnitOfWork())

    with pytest.raises(ValueError, match="No terms available"):
        await use_case.execute()


@pytest.mark.asyncio
async def test_publish_term_upserts_and_returns_it() -> None:
    uow = InMemoryUnitOfWork()
    new_term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    result = await use_case.execute(new_term)

    assert result == new_term
    assert await uow.terms.by_id("fsm") == new_term


@pytest.mark.asyncio
async def test_publish_term_publishes_term_published_event() -> None:
    uow = InMemoryUnitOfWork()
    term = Term(
        id="fsm",
        term="FSM",
        expansion="Finite State Machine",
        definitions=("A model with a finite number of states and transitions.",),
        categories=(Category(slug="theory"),),
    )
    use_case = PublishTerm(uow)

    await use_case.execute(term)

    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert events.events == [("TermPublished", {"term_id": "fsm"})]
