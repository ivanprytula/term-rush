"""KafkaEventPublisher tests: envelope shape, topic, delivery, failure handling."""

from __future__ import annotations

import json

import pytest
from aiokafka.errors import KafkaConnectionError

from content_service.infrastructure.kafka_event_publisher import TOPIC
from content_service.infrastructure.kafka_event_publisher import KafkaEventPublisher


class _FakeProducer:
    """Replaces AIOKafkaProducer: records what was sent instead of talking to a broker."""

    def __init__(self, *, fails: bool = False) -> None:
        self.sent: list[tuple[str, bytes]] = []
        self._fails = fails

    async def send_and_wait(self, topic: str, value: bytes) -> None:
        if self._fails:
            raise KafkaConnectionError("broker unreachable")
        self.sent.append((topic, value))


def _publisher(*, fails: bool = False) -> tuple[KafkaEventPublisher, _FakeProducer]:
    publisher = KafkaEventPublisher.__new__(KafkaEventPublisher)
    producer = _FakeProducer(fails=fails)
    publisher._producer = producer  # type: ignore
    return publisher, producer


@pytest.mark.asyncio
async def test_publish_sends_to_the_terms_published_topic() -> None:
    publisher, producer = _publisher()

    await publisher.publish("TermPublished", {"term_id": "uow"})

    assert len(producer.sent) == 1
    topic, _ = producer.sent[0]
    assert topic == TOPIC


@pytest.mark.asyncio
async def test_publish_serializes_the_event_envelope() -> None:
    publisher, producer = _publisher()

    await publisher.publish("TermPublished", {"term_id": "uow"})

    _, value = producer.sent[0]
    envelope = json.loads(value)
    assert envelope["event_type"] == "TermPublished"
    assert envelope["payload"] == {"term_id": "uow"}
    assert envelope["schema_version"] == 1
    assert "event_id" in envelope
    assert "occurred_at" in envelope


@pytest.mark.asyncio
async def test_publish_swallows_a_broker_failure() -> None:
    """A Kafka outage must not fail the caller's request (publishing a term)."""
    publisher, producer = _publisher(fails=True)

    await publisher.publish("TermPublished", {"term_id": "uow"})

    assert producer.sent == []
