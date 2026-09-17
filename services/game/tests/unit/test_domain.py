"""Grader chain tests.

The similarity cases are a regression oracle: they pin the values produced by
the original prototype's JavaScript similarity() so the Python port cannot
silently drift. If one of these changes, it must be a deliberate decision.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.graders import AliasGrader
from domain.graders import AnswerEvaluator
from domain.graders import ExactGrader
from domain.graders import FuzzyGrader
from domain.graders import build_deterministic_evaluator
from domain.graders import normalize
from domain.graders import token_similarity
from domain.outcome import MatchedVia
from domain.outcome import RubricBreakdown
from domain.outcome import Verdict
from domain.term import Category
from domain.term import Difficulty
from domain.term import Term


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


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Unit of Work", "unit of work"),
            ("  UNIT-OF-WORK  ", "unit of work"),
            ("TCP/IP", "tcp ip"),
            ("Don't Repeat Yourself", "don t repeat yourself"),
            ("", ""),
            ("!!!", ""),
        ],
    )
    def test_collapses_to_comparable_form(self, raw: str, expected: str) -> None:
        assert normalize(raw) == expected


class TestTokenSimilarity:
    """Values pinned from the prototype's similarity() implementation."""

    @pytest.mark.parametrize(
        ("answer", "target", "expected"),
        [
            ("Unit of Work", "Unit of Work", 1.0),
            ("unit of work", "Unit of Work", 1.0),
            ("Unit of Work pattern", "Unit of Work", 0.88),  # substring
            ("Unit of Work", "Unit of Work pattern", 0.88),  # reverse substring
            ("Work of Unit", "Unit of Work", 1.0),  # token set, order-free
            # A single word is a *substring*, so the substring rule fires at
            # 0.88 before token-overlap is reached. This is generous — see
            # ADR-0002 on why the threshold sits at 0.62 regardless.
            ("Unit", "Unit of Work", 0.88),
            ("unit work", "Unit of Work", 2 / 3),  # 2 hits / max(2, 3)
            ("", "Unit of Work", 0.0),
            ("Unit of Work", "", 0.0),
            ("totally unrelated", "Unit of Work", 0.0),
        ],
    )
    def test_matches_prototype_behaviour(
        self, answer: str, target: str, expected: float
    ) -> None:
        assert token_similarity(answer, target) == pytest.approx(expected)

    @given(st.text(), st.text())
    def test_always_in_unit_interval(self, a: str, b: str) -> None:
        assert 0.0 <= token_similarity(a, b) <= 1.0

    @given(st.text(min_size=1).filter(lambda s: normalize(s) != ""))
    def test_identity_is_perfect(self, text: str) -> None:
        assert token_similarity(text, text) == 1.0


class TestExactGrader:
    def test_accepts_exact_expansion(self, uow_term: Term) -> None:
        outcome = ExactGrader().grade("Unit of Work", uow_term)
        assert outcome is not None
        assert outcome.verdict is Verdict.CORRECT
        assert outcome.matched_via is MatchedVia.EXACT
        assert outcome.rubric.expansion == RubricBreakdown.EXPANSION_WEIGHT

    def test_ignores_case_and_punctuation(self, uow_term: Term) -> None:
        assert ExactGrader().grade("  unit OF work!  ", uow_term) is not None

    def test_abstains_on_mismatch(self, uow_term: Term) -> None:
        assert ExactGrader().grade("something else", uow_term) is None


class TestAliasGrader:
    def test_accepts_alias(self, uow_term: Term) -> None:
        outcome = AliasGrader().grade("Unit-of-Work", uow_term)
        assert outcome is not None
        assert outcome.matched_via is MatchedVia.ALIAS

    def test_abstains_when_no_alias_matches(self, uow_term: Term) -> None:
        assert AliasGrader().grade("nonsense", uow_term) is None


class TestFuzzyGrader:
    def test_never_abstains(self, uow_term: Term) -> None:
        """The last deterministic grader must always produce a verdict."""
        assert FuzzyGrader().grade("complete nonsense", uow_term) is not None

    def test_accepts_close_wording(self, uow_term: Term) -> None:
        outcome = FuzzyGrader().grade("unit of work pattern", uow_term)
        assert outcome is not None
        assert outcome.verdict is Verdict.CORRECT

    def test_partial_credit_for_half_remembered(self, uow_term: Term) -> None:
        # Scores 0.60: between FUZZY_PARTIAL_THRESHOLD and FUZZY_ACCEPT_THRESHOLD.
        outcome = FuzzyGrader().grade("work of the unit thing", uow_term)
        assert outcome is not None
        assert outcome.verdict is Verdict.PARTIAL
        assert 0 < outcome.rubric.expansion < RubricBreakdown.EXPANSION_WEIGHT

    def test_rejects_unrelated(self, uow_term: Term) -> None:
        outcome = FuzzyGrader().grade("a kind of sandwich", uow_term)
        assert outcome is not None
        assert outcome.verdict is Verdict.INCORRECT
        assert outcome.rubric.total == 0

    def test_single_word_substring_is_accepted(self, uow_term: Term) -> None:
        """Known weakness, inherited from the prototype and kept deliberately.

        "Unit" is a substring of "Unit of Work", so it scores 0.88 and passes.
        The deterministic chain cannot tell recall from a lucky prefix — that is
        precisely the gap the Phase 2 rubric judge closes, and why deterministic
        grading only ever awards the 30-point expansion slice. See ADR-0002.
        """
        outcome = FuzzyGrader().grade("Unit", uow_term)
        assert outcome is not None
        assert outcome.verdict is Verdict.CORRECT
        assert outcome.rubric.total == RubricBreakdown.EXPANSION_WEIGHT
        assert outcome.rubric.concept == 0


class TestAnswerEvaluator:
    def test_prefers_earliest_grader(self, uow_term: Term) -> None:
        """An exact answer must not fall through to the fuzzy grader."""
        outcome = build_deterministic_evaluator().evaluate("Unit of Work", uow_term)
        assert outcome.matched_via is MatchedVia.EXACT

    def test_falls_through_to_fuzzy(self, uow_term: Term) -> None:
        outcome = build_deterministic_evaluator().evaluate(
            "the unit of work thing", uow_term
        )
        assert outcome.matched_via is MatchedVia.FUZZY

    def test_always_returns_an_outcome(self, uow_term: Term) -> None:
        outcome = build_deterministic_evaluator().evaluate("", uow_term)
        assert outcome.verdict is Verdict.INCORRECT

    def test_rejects_empty_chain(self) -> None:
        with pytest.raises(ValueError, match="at least one grader"):
            AnswerEvaluator(())

    def test_raises_if_chain_exhausts(self, uow_term: Term) -> None:
        """A chain whose final grader abstains is a programming error."""
        evaluator = AnswerEvaluator((ExactGrader(),))
        with pytest.raises(RuntimeError, match="never abstain"):
            evaluator.evaluate("not the expansion", uow_term)


class TestRubricBreakdown:
    def test_weights_sum_to_one_hundred(self) -> None:
        assert (
            RubricBreakdown.EXPANSION_WEIGHT
            + RubricBreakdown.CONCEPT_WEIGHT
            + RubricBreakdown.PURPOSE_WEIGHT
            + RubricBreakdown.EXAMPLE_WEIGHT
        ) == 100

    def test_understanding_outscores_memorization(self) -> None:
        """The core product thesis, as an assertion.

        Reciting the expansion scores 30. Explaining what it is for scores 90.
        """
        memorized = RubricBreakdown.expansion_only()
        understood = RubricBreakdown(expansion=30, concept=40, purpose=20, example=0)
        assert memorized.total == 30
        assert understood.total == 90
        assert understood.total > memorized.total
