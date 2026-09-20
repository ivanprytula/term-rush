"""Term domain entity tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from content_service.domain.term import Category
from content_service.domain.term import Difficulty
from content_service.domain.term import Term


@pytest.fixture
def term() -> Term:
    return Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("Pattern that groups related changes into one unit.",),
        aliases=("Unit-of-Work",),
        categories=(Category(slug="architecture"),),
    )


def test_all_acceptable_expansions_includes_aliases(term: Term) -> None:
    assert term.all_acceptable_expansions() == ("Unit of Work", "Unit-of-Work")


def test_primary_definition_is_the_first_definition() -> None:
    term = Term(
        id="uow",
        term="UoW",
        expansion="Unit of Work",
        definitions=("First.", "Second."),
        categories=(Category(slug="architecture"),),
    )

    assert term.primary_definition == "First."


def test_is_boss_eligible_requires_examples_and_difficulty_and_length() -> None:
    def make(difficulty: Difficulty, examples: tuple[str, ...]) -> Term:
        return Term(
            id="uow",
            term="UoW",
            expansion="Unit of Work",
            definitions=("x" * 40,),
            categories=(Category(slug="architecture"),),
            difficulty=difficulty,
            examples=examples,
        )

    eligible = make(Difficulty.HARD, ("An example.",))
    too_easy = make(Difficulty.EASY, ("An example.",))
    no_examples = make(Difficulty.HARD, ())

    assert eligible.is_boss_eligible
    assert not too_easy.is_boss_eligible
    assert not no_examples.is_boss_eligible


def test_rejects_blank_definition() -> None:
    with pytest.raises(ValidationError):
        Term(
            id="uow",
            term="UoW",
            expansion="Unit of Work",
            definitions=("   ",),
            categories=(Category(slug="architecture"),),
        )


def test_is_frozen(term: Term) -> None:
    with pytest.raises(ValidationError):
        term.term = "Other"  # type: ignore
