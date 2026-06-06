import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)


class DomainEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ObservationCreated(DomainEvent):
    observation_id: str
    species_name: str
    latitude: float
    longitude: float
    source: str


class SpeciesPredicted(DomainEvent):
    species_name: str
    confidence: float
    uncertain: bool


class ObservationValidated(DomainEvent):
    observation_id: str
    validated_by: str
    is_correct: bool


def emit(event: DomainEvent) -> None:
    """Log a domain event. Future: publish to message queue."""
    _log.info("domain_event type=%s payload=%s", type(event).__name__, event.model_dump_json())
