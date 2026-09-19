"""Use case integration tests (ports + adapters)."""

from __future__ import annotations

import pytest

from application.use_cases import GetSession
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
    outcome = await use_case.execute("session-1", "uow", "Unit of Work")
    assert outcome.verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_submit_answer_caches_result(uow: InMemoryUnitOfWork) -> None:
    """Second call with same answer hits cache."""
    use_case = SubmitAnswer(uow)
    outcome1 = await use_case.execute("session-1", "uow", "Unit of Work")
    outcome2 = await use_case.execute("session-1", "uow", "Unit of Work")
    assert outcome1.verdict is outcome2.verdict


@pytest.mark.asyncio
async def test_submit_answer_publishes_event(uow: InMemoryUnitOfWork) -> None:
    """Grading publishes an AnswerGraded event."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("session-1", "uow", "Unit of Work")
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
        await use_case.execute("session-1", "nonexistent", "anything")


@pytest.mark.asyncio
async def test_submit_answer_creates_session_on_first_call(
    uow: InMemoryUnitOfWork,
) -> None:
    """A session is created and the answer recorded on first submission."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("session-1", "uow", "Unit of Work")

    session = await uow.sessions.by_id("session-1")
    assert session is not None
    assert len(session.answers) == 1
    assert session.answers[0].term_id == "uow"
    assert session.answers[0].verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_submit_answer_appends_to_existing_session(
    uow: InMemoryUnitOfWork,
) -> None:
    """A second submission in the same session appends, not replaces."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("session-1", "uow", "Unit of Work")
    await use_case.execute("session-1", "uow", "wrong answer")

    session = await uow.sessions.by_id("session-1")
    assert session is not None
    assert len(session.answers) == 2


@pytest.mark.asyncio
async def test_get_session_returns_recorded_answers(uow: InMemoryUnitOfWork) -> None:
    """Fetching a session returns what SubmitAnswer recorded."""
    await SubmitAnswer(uow).execute("session-1", "uow", "Unit of Work")

    session = await GetSession(uow).execute("session-1")
    assert session.id == "session-1"
    assert len(session.answers) == 1
    assert session.answers[0].term_id == "uow"


@pytest.mark.asyncio
async def test_get_session_not_found(uow: InMemoryUnitOfWork) -> None:
    """Fetching a nonexistent session raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await GetSession(uow).execute("nonexistent")


@pytest.mark.asyncio
async def test_submit_answer_records_cached_outcome_again(
    uow: InMemoryUnitOfWork,
) -> None:
    """A cache hit still appends a new SubmittedAnswer to the session."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("session-1", "uow", "Unit of Work")
    await use_case.execute("session-1", "uow", "Unit of Work")

    session = await uow.sessions.by_id("session-1")
    assert session is not None
    assert len(session.answers) == 2
