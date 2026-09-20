"""Kafka-backed EventPublisher: publishes onto the durable, replayable event log."""

from __future__ import annotations

import logging

from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaError
from termrush_core.events import EventEnvelope

from game_service.application.ports import EventPublisher

logger = logging.getLogger(__name__)

TOPIC = "answers.graded"


class KafkaEventPublisher(EventPublisher):
    """Wrap a shared AIOKafkaProducer; one broker connection per process.

    The producer is started/stopped by the caller (FastAPI lifespan) since
    its TCP connection must outlive any single UnitOfWork instance.
    """

    def __init__(self, producer: AIOKafkaProducer) -> None:
        self._producer = producer

    async def publish(self, event_type: str, payload: dict) -> None:
        """Publish the event. Logs and swallows a broker failure rather than
        failing the caller's request — grading an answer should not 500
        because the event log is unreachable."""
        envelope = EventEnvelope(event_type=event_type, payload=payload)
        try:
            await self._producer.send_and_wait(
                TOPIC, envelope.model_dump_json().encode()
            )
        except KafkaError:
            logger.exception("Failed to publish %s to Kafka", event_type)
