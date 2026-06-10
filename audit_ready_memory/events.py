"""Event schema for the append-only memory log.

Memory is a sequence of immutable, time-stamped events. Four kinds exist:

- ``Message``: episodic memory — one conversational turn (human or AI).
- ``Document``: semantic memory — data a user uploaded (text extracted).
- ``Recall``: a read — records which memories entered the AI's context,
  so reads are auditable, not just writes.
- ``Deletion``: an explicit lifecycle action — deletion is itself an
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


class BaseEvent(BaseModel, frozen=True):
    id: UUID = Field(default_factory=uuid4)
    timestamp: AwareDatetime = Field(default_factory=_utc_now)
    # Total-order position in the log; assigned by the store at append time.
    seq: int | None = None
    session_id: str | None = None
    source: str = "unknown"
    actor: str | None = None

    @field_validator("timestamp")
    @classmethod
    def _normalize_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class Message(BaseEvent, frozen=True):
    """Episodic memory: one conversational turn."""

    kind: Literal["message"] = "message"
    speaker: str = Field(min_length=1)
    content: str = Field(min_length=1)
    retain_until: AwareDatetime | None = None

    @field_validator("retain_until")
    @classmethod
    def _retain_until_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class Document(BaseEvent, frozen=True):
    """Semantic memory: data a user uploaded, stored as extracted text."""

    kind: Literal["document"] = "document"
    name: str = Field(min_length=1)
    media_type: str = "text/plain"
    text: str = Field(min_length=1)
    sha256: str | None = None
    retain_until: AwareDatetime | None = None

    @field_validator("retain_until")
    @classmethod
    def _retain_until_utc(cls, value: datetime | None) -> datetime | None:
        return value.astimezone(timezone.utc) if value is not None else None


class Recall(BaseEvent, frozen=True):
    """A read: which stored memories entered the AI's context for a query."""

    kind: Literal["recall"] = "recall"
    query: str = Field(min_length=1)
    recalled: tuple[UUID, ...] = ()


class Deletion(BaseEvent, frozen=True):
    """A tombstone: the targets stay in the log but are no longer readable."""

    kind: Literal["deletion"] = "deletion"
    targets: tuple[UUID, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    requested_by: str | None = None


Event = Annotated[
    Union[Message, Document, Recall, Deletion],
    Field(discriminator="kind"),
]

event_adapter: TypeAdapter[Event] = TypeAdapter(Event)


def event_from_dict(data: dict) -> Message | Document | Recall | Deletion:
    """Validate a raw mapping into the concrete event type."""
    return event_adapter.validate_python(data)


def event_to_dict(event: BaseEvent) -> dict:
    """Serialize an event to a JSON-compatible mapping."""
    return event.model_dump(mode="json")
