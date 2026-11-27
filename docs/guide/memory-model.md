# Memory Model

Memory is a sequence of immutable, time-stamped events. There is no mutable "current state"
stored anywhere. State is derived by folding the log. That single choice is what makes the
history auditable: any past state can be rebuilt exactly, and a deletion is visible as an
act rather than as an absence.

## Fields every event carries

| Field | Type | Meaning |
|---|---|---|
| `id` | `UUID` | Stable identity, generated on creation |
| `timestamp` | aware `datetime` | When it happened. Always normalized to UTC |
| `seq` | `int \| None` | Position in the log. `None` until the store assigns it |
| `session_id` | `str \| None` | Groups events from one conversation or run |
| `source` | `str` | Where it came from, e.g. `"chat"`. Defaults to `"unknown"` |
| `actor` | `str \| None` | Which agent or component produced it |

`timestamp` records when something happened; `seq` records the order it was written. They can
disagree. A backdated import has an old timestamp and a new `seq`. The log's total
order is always `seq`. Replay depends on `seq` alone, so it does not break when clocks do.

Events are frozen Pydantic models. Once created, they cannot be mutated.

## The four kinds

### `Message`

One conversational turn.

| Field | Notes |
|---|---|
| `speaker` | Required, non-empty |
| `content` | Required, non-empty |
| `retain_until` | Optional. Recalls skip the item from this moment. See [retention and deletion](retention-and-deletion.md) |

### `Document`

Data someone brought.

| Field | Notes |
|---|---|
| `name` | Required, non-empty |
| `text` | Required, non-empty. Extracted plain text |
| `media_type` | Defaults to `text/plain` |
| `sha256` | Optional digest of the original bytes |
| `retain_until` | Optional. Same rule as for messages |

Documents hold extracted text, not the original file. The digest is the link back to the
bytes if you keep them elsewhere.

### `Recall`

A read.

| Field | Notes |
|---|---|
| `query` | Required, non-empty |
| `recalled` | Tuple of ids that entered the context |

This is the event that makes reads auditable rather than invisible. Most memory systems log
what was written; the question an audit actually asks is what was *used*.

### `Deletion`

A tombstone.

| Field | Notes |
|---|---|
| `targets` | At least one id. Must be existing messages or documents |
| `reason` | Required, non-empty |
| `requested_by` | Optional. Who asked |

## Invariants

These are enforced in code and asserted in the test suite:

1. **Append-only.** The store issues no `UPDATE` and no `DELETE`. Every write adds an event
   and the edges that start or end at it.
2. **`seq` is assigned by the store and strictly increases.** Appending an event that already
   has a `seq` raises `ValueError`.
3. **`seq` survives reopening.** The store resumes from the highest `seq` in the database.
4. **Replay is a pure fold.** Same events in, same `MemoryState` out. Out-of-order or
   unsequenced events raise `ValueError` rather than replaying wrong.
5. **Deletion targets must exist and must be content.** You cannot delete a `Recall`, a
   `Deletion`, or an unknown id.
6. **Deleted content is unreachable by reads.** It is excluded from `visible_messages`,
   `visible_documents`, and search, so it cannot re-enter a model's context.
7. **Tombstones do not erase.** The targeted events remain in the log and remain retrievable
   with `get()`.

## The graph

The log is stored as a graph in ArcadeDB.

| Node | One per |
|---|---|
| `Message`, `Document`, `Recall`, `Deletion` | event of that kind. All four also match `MemoryEvent` |

| Edge | From | To |
|---|---|---|
| `NEXT` | a message | the next message with the same `session_id` |
| `RECALLED` | a `Recall` | each message or document it read |
| `DELETED` | a `Deletion` | each message or document it targeted |

Messages without a `session_id` form one chain of their own. Follow `NEXT` backwards for the
previous message. Each event and its edges are written in one transaction.

Every node has `id`, `seq`, `kind`, `timestamp`, `session_id`, and `payload` (the whole event
as JSON). Query the graph with Cypher:

```python
memory.query(
    """
    MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id})
    RETURN r.seq AS seq, r.timestamp AS at
    ORDER BY r.seq
    """,
    {"id": str(message.id)},
)
```

`query()` refuses anything that would write. It is an audit view, so it also returns deleted and
expired content, and its results should not go into a model's context.

Replay does not use the edges. It folds the events in `seq` order, as described below.

Databases written by version 0.0.2 or earlier use a flat layout, and opening one raises
`ValueError`.

## Replaying

`replay()` folds the log into a `MemoryState`:

| Attribute | Meaning |
|---|---|
| `messages`, `documents` | Everything ever written, in log order |
| `visible_messages`, `visible_documents` | The same, minus deleted |
| `deleted` | Map of deleted id to the first `Deletion` that removed it. Deleting it again adds to the log but does not change this |
| `recall_stats` | Per item: how often it was recalled and when last |
| `last_seq` | The point in the log this state corresponds to |

Pass `up_to_seq=n` to get the state as it stood after event `n`. That is the mechanism behind
the demo's replay slider, and behind the answer to "what did this system know last Tuesday?"

`recall_stats` is derived, not stored: it is accumulated from `Recall` events during the
fold. A memory that was never read has no entry.

## What determinism does and does not cover

Replay is deterministic over the memory: the same log always yields the same state, and
therefore the same context assembled for a model. It says nothing about what the model then
writes. Language models are not deterministic, and this library does not make them so. The
reproducible part is the input, which is the part an audit can act on.
