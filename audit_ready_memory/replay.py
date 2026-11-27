"""Deterministic replay: reconstruct memory state from the event log.

``replay`` is a pure fold over the ordered log. Given the same events it
always produces the same :class:`MemoryState`, which is what makes the
log auditable: any past state can be reproduced exactly, and deletion is
visible as a tombstone rather than silent absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping
from uuid import UUID

from .events import Deletion, Document, Message, Recall

ConcreteEvent = Message | Document | Recall | Deletion


@dataclass(frozen=True)
class RecallStats:
    """How often and how recently a memory entered the AI's context."""

    num_recalled: int = 0
    last_recalled_at: datetime | None = None


@dataclass(frozen=True)
class MemoryState:
    """Memory state at a point in the log (after event ``last_seq``)."""

    messages: tuple[Message, ...] = ()
    documents: tuple[Document, ...] = ()
    deleted: Mapping[UUID, Deletion] = field(default_factory=dict)
    recall_stats: Mapping[UUID, RecallStats] = field(default_factory=dict)
    last_seq: int | None = None

    @property
    def visible_messages(self) -> tuple[Message, ...]:
        """Messages in log order, excluding deleted ones."""
        return tuple(m for m in self.messages if m.id not in self.deleted)

    @property
    def visible_documents(self) -> tuple[Document, ...]:
        """Documents in log order, excluding deleted ones."""
        return tuple(d for d in self.documents if d.id not in self.deleted)

    def is_deleted(self, event_id: UUID) -> bool:
        return event_id in self.deleted

    def expired(self, as_of: datetime) -> tuple[Message | Document, ...]:
        """Visible content whose ``retain_until`` is at or before ``as_of``.

        In log order. The time is an argument, never read from the clock, so
        the state stays a function of the log alone. ``as_of`` must carry a
        timezone.
        """
        if as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        due = [
            item
            for item in (*self.visible_messages, *self.visible_documents)
            if item.retain_until is not None and item.retain_until <= as_of
        ]
        return tuple(sorted(due, key=lambda item: item.seq))


def replay(events: Iterable[ConcreteEvent]) -> MemoryState:
    """Fold an ordered event log into a :class:`MemoryState`.

    Events must be in log order with ``seq`` assigned and strictly
    increasing; raises ``ValueError`` otherwise.
    """
    messages: list[Message] = []
    documents: list[Document] = []
    deleted: dict[UUID, Deletion] = {}
    recall_stats: dict[UUID, RecallStats] = {}
    last_seq: int | None = None

    for event in events:
        if event.seq is None:
            raise ValueError(f"event {event.id} has no seq; not from the log")
        if last_seq is not None and event.seq <= last_seq:
            raise ValueError(
                f"out-of-order event: seq {event.seq} after seq {last_seq}"
            )
        last_seq = event.seq

        if isinstance(event, Message):
            messages.append(event)
        elif isinstance(event, Document):
            documents.append(event)
        elif isinstance(event, Recall):
            for target in event.recalled:
                stats = recall_stats.get(target, RecallStats())
                recall_stats[target] = RecallStats(
                    num_recalled=stats.num_recalled + 1,
                    last_recalled_at=event.timestamp,
                )
        elif isinstance(event, Deletion):
            for target in event.targets:
                # The first deletion is the one that removed the item; a later
                # one stays in the log but changes nothing.
                deleted.setdefault(target, event)

    return MemoryState(
        messages=tuple(messages),
        documents=tuple(documents),
        deleted=deleted,
        recall_stats=recall_stats,
        last_seq=last_seq,
    )
