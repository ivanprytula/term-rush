"""Cross-service event envelope: the shared shape every published event carries."""

from __future__ import annotations

import uuid
from datetime import UTC
from datetime import datetime

from pydantic import BaseModel
from pydantic import Field


class EventEnvelope(BaseModel):
    """Wraps a domain event for publication on the event log.

    `payload` is a plain dict, not a typed schema — Phase 3 proves the
    publish/consume mechanics first; a schema registry is a later concern if
    the event catalog outgrows this.
    """

    model_config = {"frozen": True}

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    payload: dict
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schema_version: int = 1
