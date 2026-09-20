import pytest
from pydantic import ValidationError
from termrush_core.events import EventEnvelope


def test_construction_defaults_id_and_timestamp() -> None:
    event = EventEnvelope(event_type="TermPublished", payload={"term_id": "uow"})

    assert event.event_type == "TermPublished"
    assert event.payload == {"term_id": "uow"}
    assert event.schema_version == 1
    assert event.event_id
    assert event.occurred_at is not None


def test_two_envelopes_get_distinct_ids() -> None:
    first = EventEnvelope(event_type="TermPublished", payload={})
    second = EventEnvelope(event_type="TermPublished", payload={})

    assert first.event_id != second.event_id


def test_round_trips_through_json() -> None:
    event = EventEnvelope(event_type="AnswerGraded", payload={"score": 90})

    restored = EventEnvelope.model_validate_json(event.model_dump_json())

    assert restored == event


def test_is_frozen() -> None:
    event = EventEnvelope(event_type="AnswerGraded", payload={})

    with pytest.raises(ValidationError):
        event.event_type = "Other"  # type: ignore
