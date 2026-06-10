"""Audit-ready, local-first memory for AI agents."""

from importlib.metadata import PackageNotFoundError, version

from .events import (
    DeletionEvent,
    Event,
    Provenance,
    RetrievalEvent,
    UtteranceEvent,
    event_from_dict,
    event_to_dict,
)
from .replay import MemoryState, RecallStats, replay
from .store import EventStore

try:
    __version__ = version("audit-ready-memory")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "DeletionEvent",
    "Event",
    "EventStore",
    "MemoryState",
    "Provenance",
    "RecallStats",
    "RetrievalEvent",
    "UtteranceEvent",
    "event_from_dict",
    "event_to_dict",
    "replay",
    "__version__",
]
