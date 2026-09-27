"""LLM rubric grader tests.

FakeJudgePort stands in for the real Anthropic adapter (Phase 2 infra, not
yet built) — these tests pin how LLMRubricGrader maps a judgment into a
GradeOutcome, not anything about a live model.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from game_service.domain.chunk_search import RetrievedChunk
from game_service.domain.llm_grader import LLMJudgment
from game_service.domain.llm_grader import LLMRubricGrader
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict
from game_service.domain.term import Category
from game_service.domain.term import Difficulty
from game_service.domain.term import Term


@pytest.fixture
def uow_term() -> Term:
    return Term(
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


class FakeJudgePort:
    def __init__(self, judgment: LLMJudgment) -> None:
        self._judgment = judgment
        self.last_context: tuple[RetrievedChunk, ...] | None = None

    async def judge(
        self, answer: str, term: Term, context: tuple[RetrievedChunk, ...] = ()
    ) -> LLMJudgment:
        self.last_context = context
        return self._judgment

    async def stream_rationale(
        self, answer: str, term: Term, context: tuple[RetrievedChunk, ...] = ()
    ) -> AsyncIterator[str]:
        self.last_context = context
        yield self._judgment.rationale


class FakeChunkSearch:
    def __init__(self, chunks: tuple[RetrievedChunk, ...] = ()) -> None:
        self._chunks = chunks
        self.last_query: str | None = None

    async def search(self, query: str, top_k: int) -> tuple[RetrievedChunk, ...]:
        self.last_query = query
        return self._chunks


class TestLLMRubricGrader:
    @pytest.mark.asyncio
    async def test_full_marks_score_correct(self, uow_term: Term) -> None:
        judgment = LLMJudgment(
            concept=40, expansion=30, purpose=20, example=10, rationale="Nailed it."
        )
        grader = LLMRubricGrader(FakeJudgePort(judgment))

        outcome = await grader.grade("groups db changes into one transaction", uow_term)

        assert outcome.verdict is Verdict.CORRECT
        assert outcome.score == 100
        assert outcome.matched_via is MatchedVia.LLM_RUBRIC
        assert outcome.confidence == 1.0
        assert outcome.feedback == "Nailed it."

    @pytest.mark.asyncio
    async def test_understanding_outscores_memorization(self, uow_term: Term) -> None:
        """ADR-0002's product thesis: concept understanding beats reciting the
        expansion. Pinned here for the LLM path the way test_domain.py pins it
        for the deterministic chain.
        """
        expansion_only = LLMJudgment(
            concept=0, expansion=30, purpose=0, example=0, rationale="Just the name."
        )
        understood = LLMJudgment(
            concept=40,
            expansion=30,
            purpose=20,
            example=0,
            rationale="Explained the pattern and its purpose.",
        )

        expansion_outcome = await LLMRubricGrader(FakeJudgePort(expansion_only)).grade(
            "Unit of Work", uow_term
        )
        understood_outcome = await LLMRubricGrader(FakeJudgePort(understood)).grade(
            "groups db changes into one transaction, for atomicity", uow_term
        )

        assert understood_outcome.score > expansion_outcome.score

    @pytest.mark.asyncio
    async def test_mid_score_is_partial(self, uow_term: Term) -> None:
        judgment = LLMJudgment(
            concept=20, expansion=20, purpose=0, example=0, rationale="Partial grasp."
        )
        outcome = await LLMRubricGrader(FakeJudgePort(judgment)).grade(
            "some database thing", uow_term
        )

        assert outcome.verdict is Verdict.PARTIAL
        assert outcome.score == 40

    @pytest.mark.asyncio
    async def test_low_score_is_incorrect(self, uow_term: Term) -> None:
        judgment = LLMJudgment(
            concept=0, expansion=0, purpose=0, example=0, rationale="Off-topic."
        )
        outcome = await LLMRubricGrader(FakeJudgePort(judgment)).grade(
            "a fruit", uow_term
        )

        assert outcome.verdict is Verdict.INCORRECT
        assert outcome.score == 0

    @pytest.mark.asyncio
    async def test_never_abstains(self, uow_term: Term) -> None:
        """Unlike the deterministic chain's non-terminal graders, this always
        produces an outcome — there is no next grader to defer to.
        """
        judgment = LLMJudgment(
            concept=0, expansion=0, purpose=0, example=0, rationale="No idea."
        )
        outcome = await LLMRubricGrader(FakeJudgePort(judgment)).grade("", uow_term)

        assert outcome is not None

    @pytest.mark.asyncio
    async def test_grade_retrieves_context_keyed_on_the_term(
        self, uow_term: Term
    ) -> None:
        """ADR-0012 Slice 2: the retrieval query is the term itself, not the
        player's answer — deterministic per term, independent of answer
        quality."""
        judgment = LLMJudgment(
            concept=40, expansion=30, purpose=20, example=10, rationale="Nailed it."
        )
        chunk_search = FakeChunkSearch()

        await LLMRubricGrader(FakeJudgePort(judgment)).grade(
            "a weak, off-topic answer", uow_term, chunk_search
        )

        assert chunk_search.last_query == "UoW Unit of Work"

    @pytest.mark.asyncio
    async def test_grade_forwards_retrieved_context_to_the_judge(
        self, uow_term: Term
    ) -> None:
        judgment = LLMJudgment(
            concept=40, expansion=30, purpose=20, example=10, rationale="Nailed it."
        )
        judge = FakeJudgePort(judgment)
        chunks = (RetrievedChunk(text="about UoW", source_file="patterns.txt"),)
        chunk_search = FakeChunkSearch(chunks)

        await LLMRubricGrader(judge).grade("answer", uow_term, chunk_search)

        assert judge.last_context == chunks

    @pytest.mark.asyncio
    async def test_grade_passes_empty_context_when_chunk_search_unconfigured(
        self, uow_term: Term
    ) -> None:
        judgment = LLMJudgment(
            concept=40, expansion=30, purpose=20, example=10, rationale="Nailed it."
        )
        judge = FakeJudgePort(judgment)

        await LLMRubricGrader(judge).grade("answer", uow_term, chunk_search=None)

        assert judge.last_context == ()

    @pytest.mark.asyncio
    async def test_stream_rationale_forwards_retrieved_context(
        self, uow_term: Term
    ) -> None:
        judgment = LLMJudgment(
            concept=40, expansion=30, purpose=20, example=10, rationale="Nailed it."
        )
        judge = FakeJudgePort(judgment)
        chunks = (RetrievedChunk(text="about UoW", source_file="patterns.txt"),)
        chunk_search = FakeChunkSearch(chunks)

        async for _ in LLMRubricGrader(judge).stream_rationale(
            "answer", uow_term, chunk_search
        ):
            pass

        assert judge.last_context == chunks


class TestLLMJudgmentValidation:
    """The port DTO is the trust boundary: the adapter must produce values
    already within rubric bounds before they reach the domain.
    """

    def test_rejects_out_of_range_concept(self) -> None:
        with pytest.raises(ValueError, match="concept"):
            LLMJudgment(concept=41, expansion=30, purpose=20, example=10, rationale="x")

    def test_rejects_negative_score(self) -> None:
        with pytest.raises(ValueError, match="expansion"):
            LLMJudgment(concept=0, expansion=-1, purpose=0, example=0, rationale="x")
