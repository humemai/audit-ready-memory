# Quick Start

This page builds a memory log, reads from it, replays an earlier state, and deletes
something. Those are the four things the library exists to do. Every snippet below runs as
written.

## Install

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
uv sync
```

## 1. Write to the log

`Memory` is a context manager over an embedded database directory. It is created on first
use.

```python
from audit_ready_memory import Memory, Message, Document

with Memory("./memory-db") as memory:
    first = memory.add_message(
        Message(speaker="anna", content="the water pump failed on tuesday")
    )
    memory.add_message(
        Message(speaker="bram", content="i logged it with the contractor")
    )
    report = memory.add_document(
        Document(name="repairs.txt", text="pump replaced on wednesday morning")
    )

    print(first.seq, report.seq)  # 0 2
```

The store assigns `seq` on append. You cannot append an event that already has one, and you
cannot change an event after the fact, because the models are frozen.

## 2. Read, and record that you read

`recall()` searches visible memory and appends a `Recall` event naming exactly what it
returned. Retrieval and its audit record are produced in one step, so they cannot disagree.

```python
with Memory("./memory-db") as memory:
    recall, hits = memory.recall("pump")

    for hit in hits:
        print(hit.seq, hit.kind)

    print(recall.recalled)  # the ids of those same hits
```

If you build context by hand, use `record_recall()` to log it yourself. Either way, the log
answers "what did the model see?", not just "what was stored?"

## 3. Replay an earlier state

`replay()` folds the log into a `MemoryState`. Pass `up_to_seq` to stop early and get the
state as it was at that point.

```python
with Memory("./memory-db") as memory:
    now = memory.replay()
    print(len(now.visible_messages), "messages")

    earlier = memory.replay(up_to_seq=0)
    print(len(earlier.visible_messages), "messages")  # 1
```

Replay is a pure function of the events. The same log always produces the same state, which
is what makes a past decision reconstructable.

## 4. Delete, with a reason

Deletion appends a tombstone. The reason is required.

```python
with Memory("./memory-db") as memory:
    target = memory.replay().visible_messages[0]

    memory.delete((target.id,), reason="resident asked us to remove it")

    state = memory.replay()
    print(state.is_deleted(target.id))                    # True
    print(target.id in [m.id for m in state.visible_messages])  # False

    # Still in the log, and still auditable.
    print(memory.get(target.id).content)
```

Deleted content is excluded from `visible_messages`, from `visible_documents`, and from
search, so it can never re-enter a model's context. It is *not* erased from the log. See
[retention and deletion](../guide/retention-and-deletion.md) for what that does and does not
give you.

## 5. Read the whole audit trail

```python
with Memory("./memory-db") as memory:
    for event in memory.events():
        print(event.seq, event.kind, event.timestamp.isoformat())
```

`events()` returns the log in `seq` order and filters on `kind`, `session_id`, `after_seq`,
and `up_to_seq`.

## Try the demo

```bash
uv run --extra demo streamlit run demo/app.py
```

A small group chats with each other and an AI, uploads documents, and can inspect the audit
log, move a replay slider, and delete entries with a reason. Without an `OPENROUTER_API_KEY`
everything except the AI chat still works.

## Next

- [Memory model](../guide/memory-model.md): the four event kinds and the invariants they hold
- [Retention and deletion](../guide/retention-and-deletion.md): safe defaults, and the
  tombstone caveat
- [API reference](../reference/api.md)
- [Limitations](../guide/limitations.md)
