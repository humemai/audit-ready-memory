"""Audit-ready, local-first memory for AI agents."""

from importlib.metadata import PackageNotFoundError, version

from .assistant import Assistant, MissingAPIKeyError, Reply
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
from .retrieval import search
from .store import Memory

try:
    __version__ = version("audit-ready-memory")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = [
    "Assistant",
    "Deletion",
    "Document",
    "Event",
    "Memory",
    "MemoryState",
    "Message",
    "MissingAPIKeyError",
    "Recall",
    "RecallStats",
    "Reply",
    "event_from_dict",
    "event_to_dict",
    "replay",
    "search",
    "__version__",
]
