"""Audit-ready, local-first memory for AI agents."""

from importlib.metadata import PackageNotFoundError, version

from .events import (
    Deletion,
    Document,
    Event,
    Message,
    Recall,
    event_from_dict,
    event_to_dict,
)
from .replay import MemoryState, RecallStats, replay
from .store import Memory

try:
    __version__ = version("audit-ready-memory")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "Deletion",
    "Document",
    "Event",
    "Memory",
    "MemoryState",
    "Message",
    "Recall",
    "RecallStats",
    "event_from_dict",
    "event_to_dict",
    "replay",
    "__version__",
]
