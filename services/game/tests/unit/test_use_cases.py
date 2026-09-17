"""Use case integration tests (ports + adapters)."""

from __future__ import annotations

import pytest

from application.use_cases import SubmitAnswer
from domain.outcome import Verdict
from domain.term import Category
from domain.term import Difficulty
from domain.term import Term
from infrastructure.memory import InMemoryUnitOfWork


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    uow_term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        aliases=("Unit-of-Work",),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.HARD,
        examples=("Committing several repository writes as one transaction.",),
    )
    return InMemoryUnitOfWork(terms={"uow": uow_term})


@pytest.mark.asyncio
async def test_submit_answer_exact_match(uow: InMemoryUnitOfWork) -> None:
    """Grading an exact answer returns CORRECT."""
    use_case = SubmitAnswer(uow)
    outcome = await use_case.execute("uow", "Unit of Work")
    assert outcome.verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_submit_answer_caches_result(uow: InMemoryUnitOfWork) -> None:
    """Second call with same answer hits cache."""
    use_case = SubmitAnswer(uow)
    outcome1 = await use_case.execute("uow", "Unit of Work")
    outcome2 = await use_case.execute("uow", "Unit of Work")
    assert outcome1.verdict is outcome2.verdict


@pytest.mark.asyncio
async def test_submit_answer_publishes_event(uow: InMemoryUnitOfWork) -> None:
    """Grading publishes an AnswerGraded event."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("uow", "Unit of Work")
    from infrastructure.memory import InMemoryEventPublisher

    events = uow.events
    assert isinstance(events, InMemoryEventPublisher)
    assert len(events.events) == 1
    event_type, payload = events.events[0]
    assert event_type == "AnswerGraded"
    assert payload["term_id"] == "uow"
    assert payload["answer"] == "Unit of Work"
    assert payload["verdict"] == "correct"


@pytest.mark.asyncio
async def test_submit_answer_term_not_found(uow: InMemoryUnitOfWork) -> None:
    """Grading a nonexistent term raises ValueError."""
    use_case = SubmitAnswer(uow)
    with pytest.raises(ValueError, match="not found"):
        await use_case.execute("nonexistent", "anything")
