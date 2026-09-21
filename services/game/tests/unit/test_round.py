"""GameRound domain entity tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

import pytest
from pydantic import ValidationError

from game_service.domain import constants
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict
from game_service.domain.round import GameRound
from game_service.domain.round import RoundExpired
from game_service.domain.round import RoundFull
from game_service.domain.round import RoundMode
from game_service.domain.round import SubmittedAnswer


@pytest.fixture
def answer() -> SubmittedAnswer:
    return SubmittedAnswer(
        term_id="uow",
        verdict=Verdict.CORRECT,
        score=30,
        matched_via=MatchedVia.EXACT,
        submitted_at=datetime.now(UTC),
    )


def test_record_appends_without_mutating_original(
    answer: SubmittedAnswer,
) -> None:
    now = datetime.now(UTC)
    round_ = GameRound(id="s1", created_at=now)

    updated = round_.record(answer, now)

    assert round_.answers == ()
    assert updated.answers == (answer,)


def test_record_preserves_existing_answers(answer: SubmittedAnswer) -> None:
    now = datetime.now(UTC)
    round_ = GameRound(id="s1", created_at=now, answers=(answer,))

    second = answer.model_copy(update={"term_id": "idempotent"})
    updated = round_.record(second, now)

    assert updated.answers == (answer, second)


def test_round_rejects_id_over_max_length() -> None:
    with pytest.raises(ValidationError):
        GameRound(id="s" * 65, created_at=datetime.now(UTC))


def test_submitted_answer_rejects_score_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        SubmittedAnswer(
            term_id="uow",
            verdict=Verdict.CORRECT,
            score=101,
            matched_via=MatchedVia.EXACT,
            submitted_at=datetime.now(UTC),
        )


def test_start_mints_a_fresh_id() -> None:
    now = datetime.now(UTC)
    first = GameRound.start(now)
    second = GameRound.start(now)

    assert first.id != second.id
    assert first.created_at == now
    assert first.answers == ()


def test_total_score_sums_answers(answer: SubmittedAnswer) -> None:
    second = answer.model_copy(update={"term_id": "leaderboard", "score": 45})
    round_ = GameRound(id="s1", created_at=datetime.now(UTC), answers=(answer, second))

    assert round_.total_score == 75


def test_total_score_zero_when_no_answers() -> None:
    round_ = GameRound(id="s1", created_at=datetime.now(UTC))

    assert round_.total_score == 0


def test_record_raises_round_full_at_max_answers(answer: SubmittedAnswer) -> None:
    now = datetime.now(UTC)
    full = GameRound(
        id="s1",
        created_at=now,
        answers=(answer,) * constants.ROUND_MAX_ANSWERS,
    )

    with pytest.raises(RoundFull):
        full.record(answer, now)


def test_start_sprint_sets_started_at_and_default_duration() -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT)

    assert round_.mode is RoundMode.SPRINT
    assert round_.started_at == now
    assert round_.duration_seconds == constants.DEFAULT_SPRINT_DURATION_SECONDS


def test_start_sprint_respects_explicit_duration() -> None:
    round_ = GameRound.start(
        datetime.now(UTC), mode=RoundMode.SPRINT, duration_seconds=30
    )

    assert round_.duration_seconds == 30


def test_start_classic_ignores_duration_seconds() -> None:
    round_ = GameRound.start(
        datetime.now(UTC), mode=RoundMode.CLASSIC, duration_seconds=30
    )

    assert round_.started_at is None
    assert round_.duration_seconds is None


def test_remaining_seconds_none_for_classic() -> None:
    round_ = GameRound.start(datetime.now(UTC))

    assert round_.remaining_seconds(datetime.now(UTC)) is None


def test_remaining_seconds_counts_down_for_sprint() -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)

    later = now + timedelta(seconds=20)

    assert round_.remaining_seconds(later) == pytest.approx(40.0)


def test_remaining_seconds_floors_at_zero_past_expiry() -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)

    later = now + timedelta(seconds=90)

    assert round_.remaining_seconds(later) == 0.0


def test_is_expired_false_for_classic_regardless_of_elapsed_time() -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now)

    assert round_.is_expired(now + timedelta(days=1)) is False


def test_is_expired_true_once_sprint_duration_elapses() -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)

    assert round_.is_expired(now + timedelta(seconds=59)) is False
    assert round_.is_expired(now + timedelta(seconds=60)) is True


def test_record_raises_round_expired_after_sprint_timer_runs_out(
    answer: SubmittedAnswer,
) -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)

    with pytest.raises(RoundExpired):
        round_.record(answer, now + timedelta(seconds=61))


def test_record_succeeds_within_sprint_window(answer: SubmittedAnswer) -> None:
    now = datetime.now(UTC)
    round_ = GameRound.start(now, mode=RoundMode.SPRINT, duration_seconds=60)

    updated = round_.record(answer, now + timedelta(seconds=30))

    assert updated.answers == (answer,)
