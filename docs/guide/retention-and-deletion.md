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

## Retention

`Message` and `Document` accept a `retain_until` timestamp. It is the moment from which the
content may no longer be used.

```python
from datetime import datetime, timedelta, timezone

from audit_ready_memory import Message

in_30_days = datetime.now(timezone.utc) + timedelta(days=30)
memory.add_message(Message(speaker="anna", content="door code 4471", retain_until=in_30_days))
```

Two things act on it.

**Reads skip expired content.** From that moment `memory.recall()` and the assistant leave the
item out, so it cannot enter a model's context. This needs no scheduled job.

**`expire()` records the removal.** It appends one `Deletion` naming everything that has
expired, so expiry shows in the audit log like any other deletion.

```python
tombstone = memory.expire(requested_by="nightly job")  # None if nothing was due
```

Until `expire()` runs, an expired item is no longer recalled but still appears in
`state.visible_messages` or `state.visible_documents`. Run it on a schedule that matches your
retention promise. The library does not schedule it for you.

`replay()` never reads the clock. To ask what had expired at a given moment, pass the time:

```python
memory.replay().expired(datetime(2026, 12, 1, tzinfo=timezone.utc))
```

`search()` takes the same kind of time as `as_of=`; without it, only deletion hides content.
`record_recall()` records whatever you give it, including an expired item, because the log has to
say what was actually read. Expiry is a deletion, so it is a tombstone too: the bytes stay in the
log.

## Safe defaults

Sensible starting positions for a deployment:

| Decision | Default | Why |
|---|---|---|
| Retention period | Set `retain_until` on everything, and run `expire()` on a schedule | An unset field never expires; the burden should be on keeping, not on deleting |
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
