"""Kafka-backed EventPublisher: publishes onto the durable, replayable event log."""

from __future__ import annotations

from aiokafka import AIOKafkaProducer
from termrush_core.events import EventEnvelope

from game_service.application.ports import EventPublisher

TOPIC = "answers.graded"


class KafkaEventPublisher(EventPublisher):
    """Wrap a shared AIOKafkaProducer; one broker connection per process.

    The producer is started/stopped by the caller (FastAPI lifespan) since
    its TCP connection must outlive any single UnitOfWork instance.
    """

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self._producer = producer

    async def publish(self, event_type: str, payload: dict) -> None:
        envelope = EventEnvelope(event_type=event_type, payload=payload)
        await self._producer.send_and_wait(TOPIC, envelope.model_dump_json().encode())
