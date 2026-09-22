"""Application use cases.

Pure business logic over ports; independent of Framework/Infrastructure.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC
from datetime import datetime
from hashlib import sha256

from game_service.application.ports import UnitOfWork
from game_service.domain.daily import daily_term_ids
from game_service.domain.graders import AnswerEvaluator
from game_service.domain.graders import build_deterministic_evaluator
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.domain.outcome import GradeOutcome
from game_service.domain.outcome import StreamEvent
from game_service.domain.outcome import StreamEventKind
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import RoundMode
from game_service.domain.round import SubmittedAnswer
from game_service.domain.term import Term
from game_service.domain.term import TermFilter

logger = logging.getLogger(__name__)


class SubmitAnswer:
    """Grade an answer against a term.

    The deterministic chain runs first and always produces an outcome; it
    caps at 30/100 (RubricBreakdown.expansion_only) because it can only
    confirm the expansion, never judge concept/purpose/example (ADR-0002).
    When the player opts into LLM grading and the deterministic verdict is
    PARTIAL — the ambiguous case the fuzzy grader itself is least sure about
    — the LLM's richer outcome replaces it. CORRECT and INCORRECT are
    trusted as-is: the LLM only adjudicates the middle. Falls back to the
    deterministic outcome if the judge fails.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        evaluator: AnswerEvaluator | None = None,
        llm_grader: LLMRubricGrader | None = None,
    ) -> None:
        self.uow = uow
        self.evaluator = evaluator or build_deterministic_evaluator()
        self.llm_grader = llm_grader

    async def execute(
        self,
        round_id: str,
        term_id: str,
        answer: str,
        use_llm_grading: bool = False,
    ) -> GradeOutcome:
        """Grade the answer and record it against the round. Return cached
        outcome if available.

        use_llm_grading: player opt-in. Only escalates when the deterministic
        chain returns PARTIAL and an llm_grader is configured; ignored
        otherwise. The round's mode can also force this on or off regardless
        of the request — see RoundMode.resolve_llm_grading (Sprint forces
        off, Boss forces on, Daily 20 forces off for cross-player fairness).

        Events (for Phase 2/3): AnswerGraded published on commit.
        """
        answer_hash = sha256(answer.encode()).hexdigest()

        async with self.uow:
            round_ = await self.uow.rounds.by_id(round_id)
            if round_ is not None:
                use_llm_grading = round_.mode.resolve_llm_grading(use_llm_grading)

            cached = await self.uow.grade_cache.get(term_id, answer_hash)
            if cached is not None:
                return await self.record(round_id, term_id, cached, round_)

            term = await self.uow.terms.by_id(term_id)
            if term is None:
                raise ValueError(f"Term {term_id} not found")

            # Grade: deterministic first (cheap, always succeeds). Escalate
            # to the LLM judge only on player opt-in and a PARTIAL verdict —
            # the case the fuzzy grader itself is least confident about.
            outcome = self.evaluator.evaluate(answer, term)
            if (
                use_llm_grading
                and self.llm_grader is not None
                and outcome.verdict is Verdict.PARTIAL
            ):
                outcome = await self._try_llm_grade(answer, term, outcome)

            return await self.persist(round_id, term_id, answer, outcome, round_)

    async def persist(
        self,
        round_id: str,
        term_id: str,
        answer: str,
        outcome: GradeOutcome,
        round_: GameRound | None = None,
    ) -> GradeOutcome:
        """Cache a freshly graded outcome, publish AnswerGraded, and record
        it against the round. Public: SubmitAnswerStreaming (which grades
        outside this use case) calls this directly instead of execute() to
        avoid re-grading and duplicating persistence logic.

        round_, if already fetched by the caller, is reused instead of a
        second by_id lookup.

        Must run inside `async with self.uow:` — the caller owns that scope,
        since execute() and the streaming path enter it at different points.
        """
        answer_hash = sha256(answer.encode()).hexdigest()
        await self.uow.grade_cache.put(term_id, answer_hash, outcome)
        await self.uow.events.publish(
            "AnswerGraded",
            {
                "term_id": term_id,
                "answer": answer,
                "verdict": outcome.verdict.value,
                "rubric": outcome.rubric.model_dump(),
                "matched_via": outcome.matched_via.value,
            },
        )
        return await self.record(round_id, term_id, outcome, round_)

    async def record(
        self,
        round_id: str,
        term_id: str,
        outcome: GradeOutcome,
        round_: GameRound | None = None,
    ) -> GradeOutcome:
        """Append outcome to the round (cached or freshly graded). Public
        for the same reason as persist() — SubmitAnswerStreaming's cache-hit
        path calls this directly.

        round_, if already fetched by the caller, is reused instead of a
        second by_id lookup.

        Raises:
            RoundExpired: the round is a Sprint round whose timer expired.
        """
        now = datetime.now(UTC)
        if round_ is None:
            round_ = await self.uow.rounds.by_id(round_id)
        if round_ is None:
            round_ = GameRound(id=round_id, created_at=now)

        round_ = round_.record(
            SubmittedAnswer(
                term_id=term_id,
                verdict=outcome.verdict,
                score=outcome.score,
                matched_via=outcome.matched_via,
                submitted_at=now,
            ),
            now,
        )
        await self.uow.rounds.save(round_)
        return outcome

    async def _try_llm_grade(
        self, answer: str, term: Term, fallback: GradeOutcome
    ) -> GradeOutcome:
        """Escalate to the LLM judge; keep the deterministic outcome on any
        failure. Broad `except Exception` is deliberate, not sloppy: a
        third-party API can fail in ways we don't control (timeout, rate
        limit, malformed response), and none of them should turn into a 500
        for the player — the deterministic fallback exists precisely for
        this. This deliberately also swallows programming bugs in the LLM
        path (a TypeError from a bad port implementation, say) rather than
        crashing the request; that's a real cost, accepted because a bug
        here is not more dangerous degraded than a provider outage, and
        `exc_info=True` below makes it visible in logs either way. Task
        cancellation is unaffected: `asyncio.CancelledError` inherits from
        BaseException, not Exception, so it is never caught here and always
        propagates.
        """
        assert self.llm_grader is not None
        try:
            return await self.llm_grader.grade(answer, term)
        except Exception:
            logger.warning(
                "LLM grader failed, using deterministic outcome",
                extra={"term_id": term.id, "matched_via": fallback.matched_via.value},
                exc_info=True,
            )
            return fallback


class SubmitAnswerStreaming:
    """Grade an answer, streaming live LLM feedback text as it generates.

    Delegates persistence to SubmitAnswer.persist()/record() rather than
    duplicating cache/round/event logic — this class only adds the
    streaming rationale on top of the same grading rules SubmitAnswer uses.
    """

    def __init__(
        self,
        uow: UnitOfWork,
        evaluator: AnswerEvaluator | None = None,
        llm_grader: LLMRubricGrader | None = None,
    ) -> None:
        self._submit_answer = SubmitAnswer(uow, evaluator, llm_grader)
        self.llm_grader = llm_grader

    @property
    def uow(self) -> UnitOfWork:
        return self._submit_answer.uow

    async def execute(
        self,
        round_id: str,
        term_id: str,
        answer: str,
        use_llm_grading: bool = False,
    ) -> AsyncIterator[StreamEvent]:
        """Yield RATIONALE_DELTA events while the LLM judge is generating
        feedback, then exactly one final GRADED event. A verdict that never
        escalates (no opt-in, not PARTIAL, or a cache hit) yields only the
        GRADED event — nothing to stream.
        """
        answer_hash = sha256(answer.encode()).hexdigest()

        async with self.uow:
            round_ = await self.uow.rounds.by_id(round_id)
            if round_ is not None:
                use_llm_grading = round_.mode.resolve_llm_grading(use_llm_grading)

            cached = await self.uow.grade_cache.get(term_id, answer_hash)
            if cached is not None:
                outcome = await self._submit_answer.record(
                    round_id, term_id, cached, round_
                )
                yield StreamEvent.graded(outcome)
                return

            term = await self.uow.terms.by_id(term_id)
            if term is None:
                raise ValueError(f"Term {term_id} not found")

            outcome = self._submit_answer.evaluator.evaluate(answer, term)
            escalate = (
                use_llm_grading
                and self.llm_grader is not None
                and outcome.verdict is Verdict.PARTIAL
            )

            if escalate:
                async for event in self._stream_and_grade(answer, term):
                    if event.kind is StreamEventKind.RATIONALE_DELTA:
                        yield event
                    elif event.outcome is not None:
                        outcome = event.outcome

            final = await self._submit_answer.persist(
                round_id, term_id, answer, outcome, round_
            )
            yield StreamEvent.graded(final)

    async def _stream_and_grade(
        self, answer: str, term: Term
    ) -> AsyncIterator[StreamEvent]:
        """Stream rationale text live, then yield the structured score as a
        final GRADED event carrying the LLM outcome (not yet persisted —
        the caller merges it and persists once). Falls back silently to the
        caller's existing deterministic outcome on any failure, same
        broad-except reasoning as SubmitAnswer._try_llm_grade.
        """
        assert self.llm_grader is not None
        try:
            async for chunk in self.llm_grader.stream_rationale(answer, term):
                yield StreamEvent.rationale_delta(chunk)
            outcome = await self.llm_grader.grade(answer, term)
            yield StreamEvent.graded(outcome)
        except Exception:
            logger.warning(
                "LLM streaming grader failed, using deterministic outcome",
                extra={"term_id": term.id},
                exc_info=True,
            )


class CreateGameRound:
    """Start a new round."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        mode: RoundMode = RoundMode.CLASSIC,
        duration_seconds: int | None = None,
    ) -> GameRound:
        """Mint a new round and persist it. duration_seconds is ignored
        outside Sprint mode.

        Raises ValueError if mode is DAILY_20 and the term bank is empty
        (or unreachable) — an empty daily set could never be played anyway.
        """
        async with self.uow:
            term_ids: tuple[str, ...] | None = None
            if mode is RoundMode.DAILY_20:
                all_ids = await self.uow.terms.all_ids()
                term_ids = daily_term_ids(datetime.now(UTC).date(), all_ids)
                if not term_ids:
                    raise ValueError("No terms available")
            round_ = GameRound.start(
                datetime.now(UTC), mode, duration_seconds, term_ids
            )
            await self.uow.rounds.save(round_)
            return round_


class GetRound:
    """Fetch a round's recorded answers."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, round_id: str) -> GameRound:
        """Return the round. Raises ValueError if it does not exist."""
        async with self.uow:
            round_ = await self.uow.rounds.by_id(round_id)
            if round_ is None:
                raise ValueError(f"Round {round_id} not found")
            return round_


class GetLeaderboard:
    """Fetch the top rounds by total score."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self, limit: int) -> list[GameRound]:
        """Return up to `limit` rounds, highest total_score first."""
        async with self.uow:
            return await self.uow.rounds.top_by_score(limit)


class GetNextTerm:
    """Fetch the term to present to the player next.

    Renamed from GetRandomTerm: Daily 20 walks its round's snapshotted
    term_ids in positional order rather than drawing randomly, so "random"
    was never an accurate name for what this use case does across every
    mode."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(
        self,
        round_id: str | None = None,
        category: str | None = None,
    ) -> Term:
        """Return the next term, optionally scoped to a category (a
        player-chosen collection: "python-keywords", "abbreviations", ...).
        Raises ValueError if no term matches (empty bank, category has no
        terms, Boss Round with no boss-eligible term, or — Daily 20 — the
        round's snapshotted term set is exhausted, which should never
        happen since is_over already gates at the same cap).

        round_id is optional: unauthenticated callers (or callers before
        a round exists) still get a plain random term, unexcluded. A Boss
        round derives its filter from the round's own mode rather than a
        caller-supplied parameter — a client should never be able to ask
        for a boss-eligible term in a Classic round, and this way GET
        /terms/random needs no new query param for it. Daily 20 skips the
        random draw entirely: it serves its round's term_ids in order,
        indexed by how many answers already exist.
        """
        async with self.uow:
            excluded_ids: frozenset[str] = frozenset()
            term_filter: TermFilter | None = None
            round_: GameRound | None = None
            if round_id is not None:
                round_ = await self.uow.rounds.by_id(round_id)
                if round_ is not None:
                    excluded_ids = frozenset(a.term_id for a in round_.answers)
                    if round_.mode is RoundMode.BOSS:
                        term_filter = TermFilter.boss_eligible()

            if round_ is not None and round_.mode is RoundMode.DAILY_20:
                assert round_.term_ids is not None  # set at creation
                index = len(round_.answers)
                if index >= len(round_.term_ids):
                    raise ValueError("Daily 20 round's term set is exhausted")
                term = await self.uow.terms.by_id(round_.term_ids[index])
                if term is None:
                    raise ValueError("No terms available")
                return term

            term = await self.uow.terms.random(excluded_ids, category, term_filter)
            if term is None:
                if term_filter is not None:
                    raise ValueError("No boss-eligible term available")
                raise ValueError("No terms available")
            return term


class ListTermCategories:
    """List every category slug present in the term bank — the collections
    a player can choose to play from."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def execute(self) -> tuple[str, ...]:
        """Return every category slug, sorted."""
        async with self.uow:
            return await self.uow.terms.categories()
