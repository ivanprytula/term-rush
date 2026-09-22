"""Use case integration tests (ports + adapters)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest

from game_service.application.use_cases import CreateGameRound
from game_service.application.use_cases import GetNextTerm
from game_service.application.use_cases import GetRound
from game_service.application.use_cases import ListTermCategories
from game_service.application.use_cases import SubmitAnswer
from game_service.application.use_cases import SubmitAnswerStreaming
from game_service.domain.llm_grader import LLMJudgment
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import StreamEventKind
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import RoundExpired
from game_service.domain.round import RoundMode
from game_service.domain.round import RoundOver
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
async def test_create_game_round_mints_and_persists(uow: InMemoryUnitOfWork) -> None:
    """Creating a round mints an id and saves an empty round under it."""
    round_ = await CreateGameRound(uow).execute()

    assert round_.answers == ()
    stored = await uow.rounds.by_id(round_.id)
    assert stored == round_


@pytest.mark.asyncio
async def test_create_game_round_sprint_sets_timer_fields(
    uow: InMemoryUnitOfWork,
) -> None:
    """Creating a Sprint round starts its countdown immediately."""
    round_ = await CreateGameRound(uow).execute(
        mode=RoundMode.SPRINT, duration_seconds=30
    )

    assert round_.mode is RoundMode.SPRINT
    assert round_.started_at is not None
    assert round_.duration_seconds == 30


@pytest.mark.asyncio
async def test_create_game_round_mints_distinct_ids(uow: InMemoryUnitOfWork) -> None:
    """Two calls produce two distinct rounds."""
    first = await CreateGameRound(uow).execute()
    second = await CreateGameRound(uow).execute()

    assert first.id != second.id


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
    term = await GetNextTerm(uow).execute()
    assert term.id == "uow"


@pytest.mark.asyncio
async def test_get_random_term_empty_bank_raises() -> None:
    """Fetching a random term from an empty bank raises ValueError."""
    empty_uow = InMemoryUnitOfWork()
    with pytest.raises(ValueError, match="No terms"):
        await GetNextTerm(empty_uow).execute()


@pytest.mark.asyncio
async def test_get_random_term_scopes_to_category() -> None:
    """category, if given, scopes the pick to that collection."""
    uow_term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        categories=(Category(slug="architecture"),),
    )
    lambda_term = Term(
        id="lambda",
        term="lambda",
        expansion="anonymous function",
        definitions=("A function defined without a name.",),
        categories=(Category(slug="python-keywords"),),
    )
    uow = InMemoryUnitOfWork(terms={"uow": uow_term, "lambda": lambda_term})

    term = await GetNextTerm(uow).execute(category="python-keywords")

    assert term.id == "lambda"


@pytest.mark.asyncio
async def test_get_random_term_raises_when_category_has_no_terms(
    uow: InMemoryUnitOfWork,
) -> None:
    """A category with no matching terms raises, same as an empty bank."""
    with pytest.raises(ValueError, match="No terms"):
        await GetNextTerm(uow).execute(category="nonexistent-category")


@pytest.mark.asyncio
async def test_list_term_categories_returns_every_distinct_slug(
    uow: InMemoryUnitOfWork,
) -> None:
    assert await ListTermCategories(uow).execute() == ("architecture",)


@pytest.mark.asyncio
async def test_get_next_term_scopes_to_boss_eligible_for_a_boss_round() -> None:
    """A Boss round's own mode derives the filter — no caller-supplied
    parameter needed. An eligible term must be drawn over an ineligible
    one sharing the same bank."""
    eligible = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=(
            "Pattern that groups related changes into one transactional unit.",
        ),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.HARD,
        examples=("Committing several repository writes as one transaction.",),
    )
    ineligible = Term(
        id="trivial-term",
        term="trivial",
        expansion="a trivial term",
        definitions=("Too short.",),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.TRIVIAL,
    )
    uow = InMemoryUnitOfWork(terms={"uow": eligible, "trivial-term": ineligible})
    boss_round = GameRound.start(datetime.now(UTC), mode=RoundMode.BOSS)
    await uow.rounds.save(boss_round)

    term = await GetNextTerm(uow).execute(round_id=boss_round.id)

    assert term.id == "uow"


@pytest.mark.asyncio
async def test_get_next_term_raises_when_no_boss_eligible_term_exists() -> None:
    """An empty-of-eligible-terms bank gets a Boss-specific message, not
    the generic 'No terms available'."""
    only_ineligible = InMemoryUnitOfWork(
        terms={
            "trivial-term": Term(
                id="trivial-term",
                term="trivial",
                expansion="a trivial term",
                definitions=("Too short.",),
                categories=(Category(slug="architecture"),),
                difficulty=Difficulty.TRIVIAL,
            )
        }
    )
    boss_round = GameRound.start(datetime.now(UTC), mode=RoundMode.BOSS)
    await only_ineligible.rounds.save(boss_round)

    with pytest.raises(ValueError, match="No boss-eligible term available"):
        await GetNextTerm(only_ineligible).execute(round_id=boss_round.id)


@pytest.mark.asyncio
async def test_get_next_term_ignores_boss_filter_for_classic_round() -> None:
    """A Classic round's own random draw is never scoped to boss-eligible —
    the filter only applies when the round's mode is BOSS."""
    ineligible = Term(
        id="trivial-term",
        term="trivial",
        expansion="a trivial term",
        definitions=("Too short.",),
        categories=(Category(slug="architecture"),),
        difficulty=Difficulty.TRIVIAL,
    )
    only_ineligible = InMemoryUnitOfWork(terms={"trivial-term": ineligible})
    classic_round = GameRound.start(datetime.now(UTC), mode=RoundMode.CLASSIC)
    await only_ineligible.rounds.save(classic_round)

    term = await GetNextTerm(only_ineligible).execute(round_id=classic_round.id)

    assert term.id == "trivial-term"


def _bank(size: int) -> dict[str, Term]:
    return {
        f"term-{i:03d}": Term(
            id=f"term-{i:03d}",
            term=f"Term {i}",
            expansion=f"expansion {i}",
            definitions=(f"Definition of term {i}.",),
            categories=(Category(slug="architecture"),),
        )
        for i in range(size)
    }


@pytest.mark.asyncio
async def test_create_daily_round_snapshots_twenty_term_ids() -> None:
    daily_uow = InMemoryUnitOfWork(terms=_bank(30))

    round_ = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)

    assert round_.term_ids is not None
    assert len(round_.term_ids) == 20


@pytest.mark.asyncio
async def test_two_daily_rounds_same_day_get_the_same_terms() -> None:
    """The headline requirement: every player starting a Daily 20 round
    today draws the same 20 terms, in the same order."""
    daily_uow = InMemoryUnitOfWork(terms=_bank(30))

    first = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)
    second = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)

    assert first.id != second.id  # distinct rounds
    assert first.term_ids == second.term_ids  # same puzzle


@pytest.mark.asyncio
async def test_create_daily_round_raises_when_bank_is_empty() -> None:
    empty_uow = InMemoryUnitOfWork()

    with pytest.raises(ValueError, match="No terms available"):
        await CreateGameRound(empty_uow).execute(mode=RoundMode.DAILY_20)


@pytest.mark.asyncio
async def test_get_next_term_serves_daily_20_terms_in_seeded_order() -> None:
    daily_uow = InMemoryUnitOfWork(terms=_bank(30))
    round_ = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)
    assert round_.term_ids is not None

    first_term = await GetNextTerm(daily_uow).execute(round_id=round_.id)

    assert first_term.id == round_.term_ids[0]


@pytest.mark.asyncio
async def test_get_next_term_serves_the_next_positional_term_after_an_answer() -> None:
    """GetNextTerm indexes by how many answers already exist — the 2nd
    fetch after 1 answer serves term_ids[1], not another draw of
    term_ids[0]."""
    daily_uow = InMemoryUnitOfWork(terms=_bank(30))
    round_ = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)
    assert round_.term_ids is not None
    await SubmitAnswer(daily_uow).execute(round_.id, round_.term_ids[0], "an answer")

    second_term = await GetNextTerm(daily_uow).execute(round_id=round_.id)

    assert second_term.id == round_.term_ids[1]


@pytest.mark.asyncio
async def test_submit_answer_raises_round_over_after_daily_20_cap_reached() -> None:
    daily_uow = InMemoryUnitOfWork(terms=_bank(25))
    round_ = await CreateGameRound(daily_uow).execute(mode=RoundMode.DAILY_20)
    assert round_.term_ids is not None
    use_case = SubmitAnswer(daily_uow)

    for term_id in round_.term_ids:
        await use_case.execute(round_.id, term_id, f"answer for {term_id}")

    with pytest.raises(RoundOver):
        await use_case.execute(round_.id, round_.term_ids[0], "one more")


@pytest.mark.asyncio
async def test_daily_20_round_completes_correctly_with_a_bank_smaller_than_twenty() -> (
    None
):
    """A bank with fewer than 20 terms degrades daily_term_ids to however
    many exist — the round must end at that real count, not silently wait
    for a 20th answer GetNextTerm could never serve. Regression coverage
    for a bug caught live: terms_remaining/is_over were originally computed
    from the DAILY_20_ROUND_SIZE constant rather than len(term_ids)."""
    small_bank_uow = InMemoryUnitOfWork(terms=_bank(10))
    round_ = await CreateGameRound(small_bank_uow).execute(mode=RoundMode.DAILY_20)
    assert round_.term_ids is not None
    assert len(round_.term_ids) == 10

    use_case = SubmitAnswer(small_bank_uow)
    for term_id in round_.term_ids:
        await use_case.execute(round_.id, term_id, f"answer for {term_id}")

    final_round = await small_bank_uow.rounds.by_id(round_.id)
    assert final_round is not None
    assert final_round.terms_remaining == 0
    assert final_round.is_over(datetime.now(UTC)) is True

    with pytest.raises(RoundOver):
        await use_case.execute(round_.id, round_.term_ids[0], "one more")


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
async def test_submit_answer_forces_off_llm_grading_in_sprint_mode(
    uow: InMemoryUnitOfWork,
) -> None:
    """Sprint rounds never escalate to the LLM judge, even with opt-in."""
    now = datetime.now(UTC)
    sprint_round = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)
    await uow.rounds.save(sprint_round)
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        sprint_round.id, "uow", "work of the unit thing", use_llm_grading=True
    )

    assert outcome.matched_via is MatchedVia.FUZZY
    assert outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_submit_answer_raises_round_expired_past_sprint_deadline(
    uow: InMemoryUnitOfWork,
) -> None:
    """A Sprint round's timer running out rejects further submissions."""
    now = datetime.now(UTC) - timedelta(seconds=61)
    sprint_round = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)
    await uow.rounds.save(sprint_round)
    use_case = SubmitAnswer(uow)

    with pytest.raises(RoundExpired):
        await use_case.execute(sprint_round.id, "uow", "Unit of Work")


@pytest.mark.asyncio
async def test_submit_answer_raises_round_over_when_survival_lives_exhausted(
    uow: InMemoryUnitOfWork,
) -> None:
    """3 wrong answers in a Survival round exhausts its lives; the 4th
    submission is rejected regardless of its own verdict. Distinct wrong
    answer text per submission so the grade cache doesn't short-circuit the
    grading path on repeats."""
    survival_round = GameRound.start(datetime.now(UTC), mode=RoundMode.SURVIVAL)
    await uow.rounds.save(survival_round)
    use_case = SubmitAnswer(uow)

    for wrong_answer in ("nonsense one", "nonsense two", "nonsense three"):
        outcome = await use_case.execute(survival_round.id, "uow", wrong_answer)
        assert outcome.verdict is Verdict.INCORRECT

    with pytest.raises(RoundOver):
        await use_case.execute(survival_round.id, "uow", "Unit of Work")


@pytest.mark.asyncio
async def test_boss_round_forces_llm_grading_on(uow: InMemoryUnitOfWork) -> None:
    """A Boss round escalates to the LLM judge even with use_llm_grading
    unset — the mode's forced-on policy, not the player's opt-in, decides."""
    judgment = LLMJudgment(
        concept=40, expansion=30, purpose=20, example=10, rationale="Full marks."
    )
    llm_grader = LLMRubricGrader(FakeJudgePort(judgment=judgment))
    boss_round = GameRound.start(datetime.now(UTC), mode=RoundMode.BOSS)
    await uow.rounds.save(boss_round)
    use_case = SubmitAnswer(uow, llm_grader=llm_grader)

    outcome = await use_case.execute(
        boss_round.id, "uow", "work of the unit thing", use_llm_grading=False
    )

    # The fuzzy grader alone would land PARTIAL; the LLM's full-marks
    # judgment landing instead proves escalation happened despite the
    # unset opt-in.
    assert outcome.verdict is Verdict.CORRECT
    assert outcome.matched_via is MatchedVia.LLM_RUBRIC


@pytest.mark.asyncio
async def test_boss_round_falls_back_to_deterministic_without_a_grader(
    uow: InMemoryUnitOfWork,
) -> None:
    """No code path exists to force escalation without a configured
    grader — SubmitAnswer only ever escalates when llm_grader is not None,
    so an unconfigured Boss round degrades to the deterministic outcome,
    same as every other mode."""
    boss_round = GameRound.start(datetime.now(UTC), mode=RoundMode.BOSS)
    await uow.rounds.save(boss_round)
    use_case = SubmitAnswer(uow)  # no llm_grader

    outcome = await use_case.execute(boss_round.id, "uow", "work of the unit thing")

    assert outcome.matched_via is MatchedVia.FUZZY
    assert outcome.verdict is Verdict.PARTIAL


@pytest.mark.asyncio
async def test_submit_answer_raises_round_over_after_boss_round_answered(
    uow: InMemoryUnitOfWork,
) -> None:
    """A Boss round accepts exactly one answer, any verdict; the second
    submission is rejected."""
    boss_round = GameRound.start(datetime.now(UTC), mode=RoundMode.BOSS)
    await uow.rounds.save(boss_round)
    use_case = SubmitAnswer(uow)

    await use_case.execute(boss_round.id, "uow", "Unit of Work")

    with pytest.raises(RoundOver):
        await use_case.execute(boss_round.id, "uow", "a second answer")


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
