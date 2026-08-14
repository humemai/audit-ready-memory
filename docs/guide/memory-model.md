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
| `retain_until` | Optional marker. **Not enforced**. See [retention and deletion](retention-and-deletion.md) |

### `Document`

Data someone brought.

| Field | Notes |
|---|---|
| `name` | Required, non-empty |
| `text` | Required, non-empty. Extracted plain text |
| `media_type` | Defaults to `text/plain` |
| `sha256` | Optional digest of the original bytes |
| `retain_until` | Optional marker. Not enforced |

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

1. **Append-only.** The store issues no `UPDATE` and no `DELETE`. Every write is an insert.
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

## Replaying

`replay()` folds the log into a `MemoryState`:

| Attribute | Meaning |
|---|---|
| `messages`, `documents` | Everything ever written, in log order |
| `visible_messages`, `visible_documents` | The same, minus deleted |
| `deleted` | Map of deleted id to the `Deletion` that did it |
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
