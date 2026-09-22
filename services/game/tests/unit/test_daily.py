"""Daily 20 domain module tests."""

from __future__ import annotations

from datetime import date

from game_service.domain.daily import daily_seed
from game_service.domain.daily import daily_term_ids


def test_daily_seed_is_stable_for_the_same_date() -> None:
    day = date(2026, 9, 22)

    assert daily_seed(day) == daily_seed(day)


def test_daily_seed_is_process_independent() -> None:
    """A literal expected value, not just self-consistency — this is what
    would catch someone swapping daily_seed's sha256 for Python's hash(),
    which is salted per-process and would break the "same puzzle for
    everyone" guarantee silently (every process still agrees with itself,
    just not with any other process)."""
    assert daily_seed(date(2026, 9, 22)) == 1757312182950086104


def test_daily_seed_differs_across_dates() -> None:
    assert daily_seed(date(2026, 9, 22)) != daily_seed(date(2026, 9, 23))


def test_daily_term_ids_is_stable_for_the_same_date() -> None:
    day = date(2026, 9, 22)
    ids = [f"term-{i:03d}" for i in range(30)]

    assert daily_term_ids(day, ids) == daily_term_ids(day, ids)


def test_daily_term_ids_differs_across_dates() -> None:
    ids = [f"term-{i:03d}" for i in range(30)]

    assert daily_term_ids(date(2026, 9, 22), ids) != daily_term_ids(
        date(2026, 9, 23), ids
    )


def test_daily_term_ids_truncates_to_size() -> None:
    day = date(2026, 9, 22)
    ids = [f"term-{i:03d}" for i in range(30)]

    result = daily_term_ids(day, ids, size=5)

    assert len(result) == 5


def test_daily_term_ids_defaults_to_twenty() -> None:
    day = date(2026, 9, 22)
    ids = [f"term-{i:03d}" for i in range(30)]

    assert len(daily_term_ids(day, ids)) == 20


def test_daily_term_ids_handles_bank_smaller_than_size() -> None:
    """A 5-term bank gives a 5-term "Daily 20" rather than erroring."""
    day = date(2026, 9, 22)
    ids = ["a", "b", "c", "d", "e"]

    result = daily_term_ids(day, ids, size=20)

    assert len(result) == 5
    assert set(result) == set(ids)


def test_daily_term_ids_draws_only_from_the_given_ids() -> None:
    day = date(2026, 9, 22)
    ids = [f"term-{i:03d}" for i in range(30)]

    result = daily_term_ids(day, ids, size=20)

    assert set(result) <= set(ids)
    assert len(set(result)) == len(result)  # no duplicates


def test_daily_term_ids_is_insensitive_to_input_order() -> None:
    """all_ids is sorted internally — an unsorted input must not silently
    change the puzzle."""
    day = date(2026, 9, 22)
    ids = [f"term-{i:03d}" for i in range(30)]

    forward = daily_term_ids(day, ids)
    shuffled = daily_term_ids(day, list(reversed(ids)))

    assert forward == shuffled
