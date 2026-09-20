"""Session domain entity tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from pydantic import ValidationError

from game_service.domain import constants
from game_service.domain.outcome import MatchedVia
from game_service.domain.outcome import Verdict
from game_service.domain.session import Session
from game_service.domain.session import SessionFull
from game_service.domain.session import SubmittedAnswer


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
    session = Session(id="s1", created_at=datetime.now(UTC))

    updated = session.record(answer)

    assert session.answers == ()
    assert updated.answers == (answer,)


def test_record_preserves_existing_answers(answer: SubmittedAnswer) -> None:
    session = Session(id="s1", created_at=datetime.now(UTC), answers=(answer,))

    second = answer.model_copy(update={"term_id": "idempotent"})
    updated = session.record(second)

    assert updated.answers == (answer, second)


def test_session_rejects_id_over_max_length() -> None:
    with pytest.raises(ValidationError):
        Session(id="s" * 65, created_at=datetime.now(UTC))


def test_submitted_answer_rejects_score_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        SubmittedAnswer(
            term_id="uow",
            verdict=Verdict.CORRECT,
            score=101,
            matched_via=MatchedVia.EXACT,
            submitted_at=datetime.now(UTC),
        )


def test_record_raises_session_full_at_max_answers(answer: SubmittedAnswer) -> None:
    full = Session(
        id="s1",
        created_at=datetime.now(UTC),
        answers=(answer,) * constants.SESSION_MAX_ANSWERS,
    )

    with pytest.raises(SessionFull):
        full.record(answer)
