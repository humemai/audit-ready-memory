"""Event schema for the append-only memory log.

Memory is a sequence of immutable, time-stamped events. Three kinds exist:

- ``UtteranceEvent``: a write — one conversational turn stored as memory.
- ``RetrievalEvent``: a read — records which memories entered an agent's
  context, so reads are auditable, not just writes.
- ``DeletionEvent``: an explicit lifecycle action — deletion is itself an
  appended event, never an in-place mutation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    TypeAdapter,
    field_validator,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Provenance(BaseModel, frozen=True):
    """Where an event came from and who produced it."""

    source: str = "unknown"
    actor: str | None = None


class BaseEvent(BaseModel, frozen=True):
    event_id: UUID = Field(default_factory=uuid4)
    timestamp: AwareDatetime = Field(default_factory=_utc_now)
    # Total-order position in the log; assigned by the store at append time.
    seq: int | None = None
    session_id: str | None = None
    provenance: Provenance = Provenance()

    @field_validator("timestamp")
    @classmethod
    def _normalize_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class UtteranceEvent(BaseEvent, frozen=True):
    kind: Literal["utterance"] = "utterance"
    speaker: str = Field(min_length=1)
    content: str = Field(min_length=1)
    retain_until: AwareDatetime | None = None

    @field_validator("retain_until")
    @classmethod
    def _retain_until_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class RetrievalEvent(BaseEvent, frozen=True):
    kind: Literal["retrieval"] = "retrieval"
    query: str = Field(min_length=1)
    retrieved_event_ids: tuple[UUID, ...] = ()


class DeletionEvent(BaseEvent, frozen=True):
    kind: Literal["deletion"] = "deletion"
    target_event_ids: tuple[UUID, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_by: str | None = None


Event = Annotated[
    Union[UtteranceEvent, RetrievalEvent, DeletionEvent],
    Field(discriminator="kind"),
]

event_adapter: TypeAdapter[Event] = TypeAdapter(Event)


def event_from_dict(data: dict) -> UtteranceEvent | RetrievalEvent | DeletionEvent:
    """Validate a raw mapping into the concrete event type."""
    return event_adapter.validate_python(data)


def event_to_dict(event: BaseEvent) -> dict:
    """Serialize an event to a JSON-compatible mapping."""
    return event.model_dump(mode="json")
