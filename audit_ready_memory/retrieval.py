"""Naive keyword retrieval over visible memory state.

Deliberately simple: lowercase word overlap between the query and each
visible message/document. Deleted content is never searched, so deleted
items can never be recalled into an AI's context. Ranking is
deterministic: overlap count descending, then log order (``seq``).
"""

from __future__ import annotations

import re

from .events import Document, Message
from .replay import MemoryState

ContentEvent = Message | Document

_WORD = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {match.group().lower() for match in _WORD.finditer(text)}


def _searchable_text(event: ContentEvent) -> str:
    if isinstance(event, Message):
        return f"{event.speaker} {event.content}"
    return f"{event.name} {event.text}"


def search(state: MemoryState, query: str, *, limit: int = 5) -> list[ContentEvent]:
    """Return up to ``limit`` visible content events matching ``query``."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    scored: list[tuple[int, ContentEvent]] = []
    for event in (*state.visible_messages, *state.visible_documents):
        overlap = len(query_tokens & _tokens(_searchable_text(event)))
        if overlap:
            scored.append((overlap, event))
    scored.sort(key=lambda pair: (-pair[0], pair[1].seq))
    return [event for _, event in scored[:limit]]
