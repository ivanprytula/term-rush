"""Term domain entity tests."""

from __future__ import annotations

from game_service.domain import constants
from game_service.domain.term import Category
from game_service.domain.term import Difficulty
from game_service.domain.term import Term
from game_service.domain.term import TermFilter


def _term(
    difficulty: Difficulty = Difficulty.HARD,
    examples: tuple[str, ...] = ("An example.",),
    definition_length: int = constants.TERM_PRIMARY_DEFINITION_MIN_LEN,
) -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("x" * definition_length,),
        categories=(Category(slug="architecture"),),
        difficulty=difficulty,
        examples=examples,
    )


def test_boss_eligible_filter_agrees_with_is_boss_eligible_at_the_difficulty_boundary() -> (
    None
):
    eligible = _term(difficulty=Difficulty.MODERATE)
    too_easy = _term(difficulty=Difficulty.EASY)

    assert eligible.is_boss_eligible
    assert TermFilter.boss_eligible().matches(eligible)
    assert not too_easy.is_boss_eligible
    assert not TermFilter.boss_eligible().matches(too_easy)


def test_boss_eligible_filter_agrees_with_is_boss_eligible_at_the_examples_boundary() -> (
    None
):
    with_example = _term(examples=("An example.",))
    without_example = _term(examples=())

    assert with_example.is_boss_eligible
    assert TermFilter.boss_eligible().matches(with_example)
    assert not without_example.is_boss_eligible
    assert not TermFilter.boss_eligible().matches(without_example)


def test_boss_eligible_filter_agrees_with_is_boss_eligible_at_the_definition_length_boundary() -> (
    None
):
    long_enough = _term(definition_length=constants.TERM_PRIMARY_DEFINITION_MIN_LEN)
    too_short = _term(definition_length=constants.TERM_PRIMARY_DEFINITION_MIN_LEN - 1)

    assert long_enough.is_boss_eligible
    assert TermFilter.boss_eligible().matches(long_enough)
    assert not too_short.is_boss_eligible
    assert not TermFilter.boss_eligible().matches(too_short)
