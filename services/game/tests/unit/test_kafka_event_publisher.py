"""KafkaEventPublisher tests: envelope shape, topic, delivery."""

from __future__ import annotations

import json

import pytest

from game_service.infrastructure.kafka_event_publisher import TOPIC
from game_service.infrastructure.kafka_event_publisher import KafkaEventPublisher


class _FakeProducer:
    """Replaces AIOKafkaProducer: records what was sent instead of talking to a broker."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, bytes]] = []

    async def send_and_wait(self, topic: str, value: bytes) -> None:
        self.sent.append((topic, value))


def _publisher() -> tuple[KafkaEventPublisher, _FakeProducer]:
    publisher = KafkaEventPublisher.__new__(KafkaEventPublisher)
    producer = _FakeProducer()
    publisher._producer = producer  # type: ignore
    return publisher, producer


@pytest.mark.asyncio
async def test_publish_sends_to_the_answers_graded_topic() -> None:
    publisher, producer = _publisher()

    await publisher.publish("AnswerGraded", {"term_id": "uow", "verdict": "correct"})

    assert len(producer.sent) == 1
    topic, _ = producer.sent[0]
    assert topic == TOPIC


@pytest.mark.asyncio
async def test_publish_serializes_the_event_envelope() -> None:
    publisher, producer = _publisher()

    await publisher.publish("AnswerGraded", {"term_id": "uow", "verdict": "correct"})

    _, value = producer.sent[0]
    envelope = json.loads(value)
    assert envelope["event_type"] == "AnswerGraded"
    assert envelope["payload"] == {"term_id": "uow", "verdict": "correct"}
    assert envelope["schema_version"] == 1
    assert "event_id" in envelope
    assert "occurred_at" in envelope
