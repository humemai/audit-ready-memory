# API Reference

Everything below is exported from the top-level package:

```python
from audit_ready_memory import Memory, Message, Document, Recall, Deletion
```

## `Memory`

An append-only log persisted in an embedded ArcadeDB database.

```python
Memory(path: str | Path)
```

Opens the database at `path`, creating it and its schema if absent. Use it as a context
manager, or call `close()` yourself.

### Writing

| Method | Returns | Notes |
|---|---|---|
| `add_message(message)` | the stored `Message` | Returns a copy with `seq` assigned |
| `add_document(document)` | the stored `Document` | Same |
| `record_recall(recall)` | the stored `Recall` | Every id in `recalled` must be an existing message or document |
| `delete(targets, reason, *, requested_by=None, session_id=None)` | the stored `Deletion` | `targets` must all be existing messages or documents |

Passing an event that already has a `seq` raises `ValueError`. An event belongs to the log
once, and cannot be re-appended.

### Reading

```python
recall(query, *, limit=5, session_id=None, source="unknown", actor=None)
    -> tuple[Recall, list[Message | Document]]
```

Searches visible memory and appends a `Recall` naming exactly what it returned. Prefer this
over calling `search()` and `record_recall()` separately: it is the reason the audit record
cannot drift from what was actually retrieved.

```python
get(event_id) -> Message | Document | Recall | Deletion | None
```

Fetches one event by id, deleted or not. Returns `None` if unknown.

```python
events(*, kind=None, session_id=None, after_seq=None, up_to_seq=None) -> list[event]
```

The log in ascending `seq` order. `kind` takes the literal discriminator: `"message"`,
`"document"`, `"recall"`, `"deletion"`.

```python
replay(*, up_to_seq=None) -> MemoryState
```

Folds the log into a state. With `up_to_seq`, the state as it stood after that event.

```python
len(memory) -> int
```

Total events in the log, including deleted content and tombstones.

## `MemoryState`

A frozen snapshot produced by `replay()`.

| Attribute | Type | |
|---|---|---|
| `messages` | `tuple[Message, ...]` | All, in log order |
| `documents` | `tuple[Document, ...]` | All, in log order |
| `visible_messages` | `tuple[Message, ...]` | Property. Excludes deleted |
| `visible_documents` | `tuple[Document, ...]` | Property. Excludes deleted |
| `deleted` | `Mapping[UUID, Deletion]` | Deleted id to the tombstone that did it |
| `recall_stats` | `Mapping[UUID, RecallStats]` | Derived from `Recall` events |
| `last_seq` | `int \| None` | The log position this state reflects |

`is_deleted(event_id) -> bool` is the readable form of `event_id in state.deleted`.

`RecallStats` has `num_recalled: int` and `last_recalled_at: datetime | None`.

## `replay`

```python
replay(events: Iterable[event]) -> MemoryState
```

The fold itself, usable on any ordered sequence of events, not only one from a store. Every
event needs a `seq`, and they must strictly increase; otherwise `ValueError`. That strictness
is deliberate: silently replaying a shuffled log would produce a state nobody can trust.

## `search`

```python
search(state: MemoryState, query: str, *, limit=5) -> list[Message | Document]
```

Lowercase word-overlap between the query and each visible message or document, ranked by
overlap count then log order. Deterministic, and blind to deleted content. An empty or
punctuation-only query returns nothing.

## Events

All four are frozen. See [memory model](../guide/memory-model.md) for the field tables.

```python
Message(speaker=..., content=..., retain_until=None, ...)
Document(name=..., text=..., media_type="text/plain", sha256=None, retain_until=None, ...)
Recall(query=..., recalled=(), ...)
Deletion(targets=(...), reason=..., requested_by=None, ...)
```

Common keyword arguments on all of them: `id`, `timestamp`, `session_id`, `source`, `actor`.
Leave `seq` alone. The store sets it.

### Serialization

```python
event_to_dict(event) -> dict     # JSON-compatible
event_from_dict(data) -> event   # dispatches on "kind"
```

Round-trips through JSON without loss. `Event` is the discriminated union if you need it for
type annotations.

## `Assistant`

An optional convenience wrapper that talks to any OpenAI-compatible endpoint, OpenRouter by
default.

```python
Assistant(
    memory,
    *,
    client=None, api_key=None, base_url=OPENROUTER_BASE_URL,
    model="openai/gpt-4o-mini", system_prompt=DEFAULT_SYSTEM_PROMPT,
    name="assistant", recall_limit=5, recent_turns=10,
)
```

Raises `MissingAPIKeyError` if no key is given and `OPENROUTER_API_KEY` is unset. Pass
`client=` to inject your own. That is how the test suite runs without a network.

```python
reply(prompt, *, speaker, session_id=None) -> Reply
```

Logs the incoming message, assembles context from recent turns plus keyword matches, appends
the `Recall` **before** calling the model, calls it, then logs the answer. `Reply` carries
`message`, `recall`, and `recalled`.

The ordering matters: the audit record is written before the content leaves the machine, so a
failed call still leaves a truthful record of what was about to be sent.

!!! warning
    The model call is a network call. Memory stays local; the recalled text does not. Point
    `base_url` at a local endpoint such as Ollama if that is unacceptable.
