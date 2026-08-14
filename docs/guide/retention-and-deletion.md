# Retention and Deletion

What deletion in this library does, what it does not do, and how to configure it safely.
Read this before deploying anywhere real data lands.

## Deletion is a tombstone

Deleting appends a `Deletion` event naming its targets and a required reason. From that point
the targeted content is excluded from every read path. The original events stay in the log.

```python
memory.delete((event_id,), reason="resident asked us to remove it", requested_by="anna")
```

After that call:

- `state.visible_messages` and `state.visible_documents` exclude it
- `search()` cannot return it, so it cannot re-enter a model's context
- `state.is_deleted(event_id)` is `True`, and `state.deleted[event_id]` is the `Deletion`
- `memory.get(event_id)` **still returns the original content**

That last line is the trade-off, stated plainly.

### Why it works this way

An append-only log is the reason any of the audit guarantees hold. If deletion rewrote
history, you could no longer prove what the system knew at a past point, and a deletion
itself would be unprovable. The strongest evidence that data was removed on request is a
durable record of the removal.

### When that is not enough

If your obligation is that the bytes cease to exist on disk, for example a GDPR erasure
request you have decided to honor literally or a legal hold expiring, **this library does
not do that for you today.** Options:

- Keep sensitive content outside the log. Store a `Document` whose `text` is a reference or
  a redacted summary, hold the payload in a store you can hard-delete, and use `sha256` to
  tie them together. The log then proves what happened without containing the material.
- Treat the whole database as the unit of disposal: it is one local directory, so retention
  at the deployment level can be a delete of that directory.
- Compact the log yourself: replay to a `MemoryState`, write a fresh database from the
  visible events only, and keep the tombstones as evidence. This breaks `seq` continuity with
  the old log, so record why you did it.

## `retain_until` is not enforced

`Message` and `Document` accept a `retain_until` timestamp. **Nothing acts on it.** No
component reads the field: not the store, not `replay()`, not `search()`. An event whose
`retain_until` passed an hour ago is still stored, still replayed as visible, still
searchable, and still eligible to enter a model's context.

Treat it today as a **marker you set and enforce yourself**:

```python
from datetime import datetime, timezone

state = memory.replay()
now = datetime.now(timezone.utc)
expired = [
    m.id for m in state.visible_messages
    if m.retain_until is not None and m.retain_until < now
]
if expired:
    memory.delete(tuple(expired), reason="retention period elapsed")
```

Run that on a schedule and the field becomes a policy. Until enforcement is built in, do not
document it to your own users as one.

## Safe defaults

Sensible starting positions for a deployment:

| Decision | Default | Why |
|---|---|---|
| Retention period | Set `retain_until` on everything, and sweep it | An unset field never expires; the burden should be on keeping, not on deleting |
| Deletion reason | Always specific and user-facing | It is already required; a reason of `"cleanup"` is worthless in an audit six months later |
| `requested_by` | Fill it whenever a person asked | Distinguishes a subject request from routine housekeeping |
| Database location | A directory you control, backed up as a unit | Local-first only helps if you know where the file is |
| File permissions | Restrict the database directory to the service user | The log is plain content on disk; there is no encryption at rest |
| Sensitive payloads | Keep out of the log; reference them | The only reliable way to hard-delete today |
| Session boundaries | Set `session_id` on every event | Deletion and audit scoped to one conversation is far easier |

## Auditing what happened

Deletions are events, so they read like any other history:

```python
for event in memory.events(kind="deletion"):
    print(event.timestamp, event.reason, event.requested_by, len(event.targets))
```

To show that a specific item was removed and when:

```python
state = memory.replay()
tombstone = state.deleted.get(event_id)
print(tombstone.timestamp, tombstone.reason)
```

## Security notes

- **No encryption at rest.** Content is readable by anyone who can read the directory.
- **No integrity chaining.** Events are ordered by `seq`, but the log is not hash-chained or
  signed. Someone with write access to the database file can alter history without leaving a
  trace. The guarantees here are against *accidental* mutation and *application-level*
  overwrites, not against a determined operator.
- **The log records content in plain text**, including whatever a user typed. Deletion is the
  only redaction mechanism.
