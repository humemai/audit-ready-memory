"""LLM assistant wired to the audit-ready memory.

The assistant talks to any OpenAI-compatible endpoint (OpenRouter by
default). Every piece of stored memory that enters the model's context is
recorded as a ``Recall`` event *before* the model is called, so the audit
log and the actual context cannot diverge. The API key lives in the
``OPENROUTER_API_KEY`` environment variable; it is never written to the
memory database or the log.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .events import Document, Message, Recall
from .retrieval import ContentEvent, search
from .store import Memory

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant embedded in a small group's shared "
    "workspace. You can see a slice of the group's memory: recent "
    "conversation turns and excerpts of uploaded documents. Everything "
    "you were shown is listed below; you have no other knowledge of the "
    "group. Answer based on that memory, and say so plainly when the "
    "memory does not contain the answer."
)

_MAX_DOCUMENT_CHARS = 4000


class MissingAPIKeyError(RuntimeError):
    """Raised when no API key is configured for the LLM endpoint."""


@dataclass(frozen=True)
class Reply:
    """Outcome of one assistant turn, fully recorded in the log."""

    message: Message
    recall: Recall
    recalled: tuple[ContentEvent, ...]


def _format_context(items: tuple[ContentEvent, ...]) -> str:
    documents = [item for item in items if isinstance(item, Document)]
    messages = [item for item in items if isinstance(item, Message)]
    parts = []
    if documents:
        blocks = [
            f"[document: {doc.name}]\n{doc.text[:_MAX_DOCUMENT_CHARS]}"
            for doc in documents
        ]
        parts.append("Shared documents:\n\n" + "\n\n".join(blocks))
    if messages:
        lines = [f"{message.speaker}: {message.content}" for message in messages]
        parts.append("Conversation:\n\n" + "\n".join(lines))
    if not parts:
        return "The group's memory is empty."
    return "\n\n".join(parts)


class Assistant:
    """One AI group member backed by an audit-ready :class:`Memory`."""

    def __init__(
        self,
        memory: Memory,
        *,
        client=None,
        api_key: str | None = None,
        base_url: str = OPENROUTER_BASE_URL,
        model: str = DEFAULT_MODEL,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        name: str = "assistant",
        recall_limit: int = 5,
        recent_turns: int = 10,
    ):
        if client is None:
            api_key = api_key or os.environ.get(API_KEY_ENV_VAR)
            if not api_key:
                raise MissingAPIKeyError(
                    f"set {API_KEY_ENV_VAR} or pass api_key= to enable chat"
                )
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=api_key)
        self._memory = memory
        self._client = client
        self.model = model
        self.system_prompt = system_prompt
        self.name = name
        self.recall_limit = recall_limit
        self.recent_turns = recent_turns

    def _gather_context(self, query: str) -> list[ContentEvent]:
        """Recent turns plus keyword matches, deduplicated, in log order."""
        state = self._memory.replay()
        recent = state.visible_messages[-self.recent_turns :]
        found = search(state, query, limit=self.recall_limit)
        by_id = {item.id: item for item in (*recent, *found)}
        return sorted(by_id.values(), key=lambda item: item.seq)

    def reply(self, prompt: str, *, speaker: str, session_id: str | None = None) -> Reply:
        """Log the incoming message, recall context, ask the LLM, log its reply."""
        self._memory.add_message(
            Message(speaker=speaker, content=prompt, source="chat", session_id=session_id)
        )
        items = tuple(self._gather_context(prompt))
        recall = self._memory.record_recall(
            Recall(
                query=prompt,
                recalled=tuple(item.id for item in items),
                source="chat",
                actor=self.name,
                session_id=session_id,
            )
        )
        completion = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": _format_context(items)},
            ],
        )
        content = completion.choices[0].message.content or "(empty reply)"
        message = self._memory.add_message(
            Message(
                speaker=self.name,
                content=content,
                source="chat",
                actor=self.name,
                session_id=session_id,
            )
        )
        return Reply(message=message, recall=recall, recalled=items)
