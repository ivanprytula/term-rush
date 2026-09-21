"""Use case integration tests (ports + adapters)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from game_service.application.use_cases import GetRandomTerm
from game_service.application.use_cases import GetRound
from game_service.application.use_cases import SubmitAnswer
from game_service.application.use_cases import SubmitAnswerStreaming
from game_service.domain.llm_grader import LLMJudgment
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import StreamEventKind
from game_service.domain.outcome import Verdict
from game_service.domain.term import Category
from game_service.domain.term import Difficulty
from game_service.domain.term import Term
from game_service.infrastructure.memory import InMemoryUnitOfWork


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
    outcome = await use_case.execute("round-1", "uow", "Unit of Work")
    assert outcome.verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_submit_answer_caches_result(uow: InMemoryUnitOfWork) -> None:
    """Second call with same answer hits cache."""
    use_case = SubmitAnswer(uow)
    outcome1 = await use_case.execute("round-1", "uow", "Unit of Work")
    outcome2 = await use_case.execute("round-1", "uow", "Unit of Work")
    assert outcome1.verdict is outcome2.verdict


@pytest.mark.asyncio
async def test_submit_answer_publishes_event(uow: InMemoryUnitOfWork) -> None:
    """Grading publishes an AnswerGraded event."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("round-1", "uow", "Unit of Work")
    from game_service.infrastructure.memory import InMemoryEventPublisher

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
        await use_case.execute("round-1", "nonexistent", "anything")


@pytest.mark.asyncio
async def test_submit_answer_creates_round_on_first_call(
    uow: InMemoryUnitOfWork,
) -> None:
    """A round is created and the answer recorded on first submission."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("round-1", "uow", "Unit of Work")

    round_ = await uow.rounds.by_id("round-1")
    assert round_ is not None
    assert len(round_.answers) == 1
    assert round_.answers[0].term_id == "uow"
    assert round_.answers[0].verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_submit_answer_appends_to_existing_round(
    uow: InMemoryUnitOfWork,
) -> None:
    """A second submission in the same round appends, not replaces."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("round-1", "uow", "Unit of Work")
    await use_case.execute("round-1", "uow", "wrong answer")

    round_ = await uow.rounds.by_id("round-1")
    assert round_ is not None
    assert len(round_.answers) == 2


@pytest.mark.asyncio
async def test_get_round_returns_recorded_answers(uow: InMemoryUnitOfWork) -> None:
    """Fetching a round returns what SubmitAnswer recorded."""
    await SubmitAnswer(uow).execute("round-1", "uow", "Unit of Work")

    round_ = await GetRound(uow).execute("round-1")
    assert round_.id == "round-1"
    assert len(round_.answers) == 1
    assert round_.answers[0].term_id == "uow"


@pytest.mark.asyncio
async def test_get_round_not_found(uow: InMemoryUnitOfWork) -> None:
    """Fetching a nonexistent round raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await GetRound(uow).execute("nonexistent")


@pytest.mark.asyncio
async def test_submit_answer_records_cached_outcome_again(
    uow: InMemoryUnitOfWork,
) -> None:
    """A cache hit still appends a new SubmittedAnswer to the round."""
    use_case = SubmitAnswer(uow)
    await use_case.execute("round-1", "uow", "Unit of Work")
    await use_case.execute("round-1", "uow", "Unit of Work")

    round_ = await uow.rounds.by_id("round-1")
    assert round_ is not None
    assert len(round_.answers) == 2


@pytest.mark.asyncio
async def test_get_random_term_returns_a_seeded_term(uow: InMemoryUnitOfWork) -> None:
    """Fetching a random term returns one from the term bank."""
    term = await GetRandomTerm(uow).execute()
    assert term.id == "uow"


@pytest.mark.asyncio
async def test_get_random_term_empty_bank_raises() -> None:
    """Fetching a random term from an empty bank raises ValueError."""
    empty_uow = InMemoryUnitOfWork()
    with pytest.raises(ValueError, match="No terms"):
        await GetRandomTerm(empty_uow).execute()


class FakeJudgePort:
    def __init__(
        self,
        judgment: LLMJudgment | None = None,
        error: BaseException | None = None,
        rationale_chunks: tuple[str, ...] | None = None,
        error_during_stream: bool = False,
    ) -> None:
        self._judgment = judgment
        self._error = error
        self._rationale_chunks = rationale_chunks
        self._error_during_stream = error_during_stream

    async def judge(self, answer: str, term: Term) -> LLMJudgment:
        if self._error is not None:
            raise self._error
        assert self._judgment is not None
        return self._judgment

    async def stream_rationale(self, answer: str, term: Term) -> AsyncIterator[str]:
        if self._error is not None and not self._error_during_stream:
            raise self._error
        chunks = self._rationale_chunks or (
            (self._judgment.rationale,) if self._judgment else ()
        )
        for chunk in chunks:
            yield chunk
        if self._error is not None and self._error_during_stream:
            raise self._error


@pytest.mark.asyncio
async def test_submit_answer_escalates_on_partial_when_opted_in(
    uow: InMemoryUnitOfWork,
) -> None:
    """Deterministic PARTIAL + opt-in + configured grader -> LLM outcome."""
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        "round-1", "uow", "work of the unit thing", use_llm_grading=True
    )

    assert outcome.matched_via is MatchedVia.LLM_RUBRIC
    assert outcome.score == 100


@pytest.mark.asyncio
async def test_submit_answer_ignores_llm_grader_without_opt_in(
    uow: InMemoryUnitOfWork,
) -> None:
    """A configured grader is not consulted unless use_llm_grading is True."""
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute("round-1", "uow", "work of the unit thing")

    assert outcome.matched_via is MatchedVia.FUZZY
    assert outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_submit_answer_skips_llm_grader_when_not_partial(
    uow: InMemoryUnitOfWork,
) -> None:
    """Opted in, but the deterministic verdict is CORRECT (exact match) —
    only PARTIAL escalates.
    """
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        "round-1", "uow", "Unit of Work", use_llm_grading=True
    )

    assert outcome.matched_via is MatchedVia.EXACT


@pytest.mark.asyncio
async def test_submit_answer_falls_back_when_llm_grader_fails(
    uow: InMemoryUnitOfWork,
) -> None:
    """A provider failure on an escalated PARTIAL keeps the deterministic
    outcome instead of raising.
    """
    llm_grader = LLMRubricGrader(FakeJudgePort(error=TimeoutError("provider down")))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        "round-1", "uow", "work of the unit thing", use_llm_grading=True
    )

    assert outcome.matched_via is MatchedVia.FUZZY
    assert outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_submit_answer_falls_back_on_a_bug_in_the_llm_path(
    uow: InMemoryUnitOfWork,
) -> None:
    """The fallback isn't provider-error-specific: a programming bug in the
    LLM path (TypeError, not a network/timeout failure) also falls back
    rather than 500ing the request. See _try_llm_grade's docstring for why
    that trade-off is accepted.
    """
    llm_grader = LLMRubricGrader(
        FakeJudgePort(error=TypeError("bad port implementation"))
    )
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        "round-1", "uow", "work of the unit thing", use_llm_grading=True
    )

    assert outcome.matched_via is MatchedVia.FUZZY
    assert outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_submit_answer_propagates_cancellation(uow: InMemoryUnitOfWork) -> None:
    """Task cancellation is not a provider failure to fall back from — it
    must propagate, not be swallowed by the broad except in _try_llm_grade.
    """
    llm_grader = LLMRubricGrader(FakeJudgePort(error=asyncio.CancelledError()))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    with pytest.raises(asyncio.CancelledError):
        await use_case.execute(
            "round-1", "uow", "work of the unit thing", use_llm_grading=True
        )


@pytest.mark.asyncio
async def test_submit_answer_without_llm_grader_stays_deterministic(
    uow: InMemoryUnitOfWork,
) -> None:
    """No llm_grader configured: behaviour is unchanged even with opt-in."""
    outcome = await SubmitAnswer(uow).execute(
        "round-1", "uow", "work of the unit thing", use_llm_grading=True
    )
    assert outcome.matched_via is MatchedVia.FUZZY


@pytest.mark.asyncio
async def test_streaming_yields_deltas_then_one_graded_event_on_escalation(
    uow: InMemoryUnitOfWork,
) -> None:
    """PARTIAL + opt-in: rationale streams live, then a single final GRADED
    event carries the LLM's structured score.
    """
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(
        FakeJudgePort(judgment=judgment, rationale_chunks=("Full ", "marks."))
    )
    use_case = SubmitAnswerStreaming(uow, llm_grader=llm_grader)

    events = [
        event
        async for event in use_case.execute(
            "round-1", "uow", "work of the unit thing", use_llm_grading=True
        )
    ]

    assert [e.kind for e in events] == [
        StreamEventKind.RATIONALE_DELTA,
        StreamEventKind.RATIONALE_DELTA,
        StreamEventKind.GRADED,
    ]
    assert events[0].text == "Full "
    assert events[1].text == "marks."
    graded = events[-1]
    assert graded.outcome is not None
    assert graded.outcome.matched_via is MatchedVia.LLM_RUBRIC
    assert graded.outcome.score == 100


@pytest.mark.asyncio
async def test_streaming_yields_only_graded_event_when_not_escalating(
    uow: InMemoryUnitOfWork,
) -> None:
    """CORRECT (exact match), opted in: nothing to stream, one GRADED event."""
    use_case = SubmitAnswerStreaming(uow)

    events = [
        event
        async for event in use_case.execute(
            "round-1", "uow", "Unit of Work", use_llm_grading=True
        )
    ]

    assert [e.kind for e in events] == [StreamEventKind.GRADED]
    assert events[0].outcome is not None
    assert events[0].outcome.matched_via is MatchedVia.EXACT


@pytest.mark.asyncio
async def test_streaming_yields_only_graded_event_on_cache_hit(
    uow: InMemoryUnitOfWork,
) -> None:
    """A cached outcome has nothing new to stream — one immediate GRADED
    event, same as any other non-escalating case.
    """
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))

    # First call grades fresh (escalates, populates the cache).
    async for _ in SubmitAnswerStreaming(uow, llm_grader=llm_grader).execute(
        "round-1", "uow", "work of the unit thing", use_llm_grading=True
    ):
        pass

    # Second call with the identical answer hits the cache.
    events = [
        event
        async for event in SubmitAnswerStreaming(uow, llm_grader=llm_grader).execute(
            "round-2", "uow", "work of the unit thing", use_llm_grading=True
        )
    ]

    assert [e.kind for e in events] == [StreamEventKind.GRADED]
    assert events[0].outcome is not None
    assert events[0].outcome.matched_via is MatchedVia.LLM_RUBRIC


@pytest.mark.asyncio
async def test_streaming_falls_back_to_deterministic_on_llm_failure(
    uow: InMemoryUnitOfWork,
) -> None:
    """A provider failure mid-stream keeps the deterministic outcome as the
    final GRADED event, same fallback contract as SubmitAnswer.
    """
    llm_grader = LLMRubricGrader(
        FakeJudgePort(
            error=TimeoutError("provider down"),
            rationale_chunks=("Partial ",),
            error_during_stream=True,
        )
    )
    use_case = SubmitAnswerStreaming(uow, llm_grader=llm_grader)

    events = [
        event
        async for event in use_case.execute(
            "round-1", "uow", "work of the unit thing", use_llm_grading=True
        )
    ]

    assert events[-1].kind is StreamEventKind.GRADED
    assert events[-1].outcome is not None
    assert events[-1].outcome.matched_via is MatchedVia.FUZZY
    assert events[-1].outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_streaming_persists_to_round(uow: InMemoryUnitOfWork) -> None:
    """The final graded outcome is recorded against the round, same as
    the non-streaming path.
    """
    use_case = SubmitAnswerStreaming(uow)

    async for _ in use_case.execute("round-1", "uow", "Unit of Work"):
        pass

    round_ = await uow.rounds.by_id("round-1")
    assert round_ is not None
    assert len(round_.answers) == 1
    assert round_.answers[0].verdict is Verdict.CORRECT


@pytest.mark.asyncio
async def test_streaming_term_not_found(uow: InMemoryUnitOfWork) -> None:
    use_case = SubmitAnswerStreaming(uow)
    with pytest.raises(ValueError, match="not found"):
        async for _ in use_case.execute("round-1", "nonexistent", "anything"):
            pass
