# audit-ready-memory

Audit-ready, local-first memory for AI agents: a time-stamped log you can read, replay, and
delete from, instead of hidden state inside a model or a hosted service.

Memory is stored as an append-only sequence of events in an embedded
[ArcadeDB](https://arcadedb.com/) database. Nothing is ever updated in place. Reads are
recorded as well as writes, so you can answer "what did the model actually see, and when?"
Deletion is an appended tombstone with a required reason, and deleted content can never
re-enter a model's context.

Funded by [SIDN Fund](https://www.sidnfonds.nl/).

## Install

The package on PyPI is not current yet; install from source until `v0.1.0` is released:

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
uv sync
```

Python 3.10 or newer. The database is embedded, so there is no server to run.

## Thirty-second example

```python
from audit_ready_memory import Memory, Message, Document

with Memory("./memory-db") as memory:
    memory.add_message(Message(speaker="anna", content="the water pump failed on tuesday"))
    memory.add_document(Document(name="repairs.txt", text="pump replaced on wednesday"))

    # Search, and record the search in the same step.
    recall, hits = memory.recall("pump")
    for hit in hits:
        print(hit.seq, hit.kind)

    # The read is now in the log too.
    print(len(memory), "events")
```

Every event carries an `id`, a UTC `timestamp`, and a `seq` assigned by the store. `seq`
gives the log a total order that does not depend on the clock.

## What you get

| Capability | How |
|---|---|
| Read the whole history | `memory.events()`, filterable by kind, session, or `seq` range |
| Rebuild any past state | `memory.replay(up_to_seq=n)`, a pure fold over the log |
| See what the model saw | every read appends a `Recall` event naming the exact items |
| Delete with a reason | `memory.delete(ids, reason="...")` appends a tombstone |
| Run it anywhere | embedded database, no server, no network |

## Four kinds of event

- **`Message`** is one conversational turn. Who said what.
- **`Document`** is data someone uploaded, stored as extracted text.
- **`Recall`** is a read. It names which stored items entered the model's context, and for
  which query.
- **`Deletion`** is a tombstone naming its targets and why they were removed.

Read the [memory model](https://docs.humem.ai/audit-ready-memory/latest/guide/memory-model/)
for the invariants these guarantee.

## Demo

A Streamlit app showing a small group chatting with each other and an AI, sharing documents,
on top of an audit-ready memory:

```bash
uv run --extra demo streamlit run demo/app.py
```

Without an `OPENROUTER_API_KEY` the app still runs. Browsing, the audit log, replay, and
deletion all work. Only the AI chat is disabled.

## Honest limits

- **Deletion is a tombstone, not erasure.** Deleted content stays in the append-only log and
  is excluded from every read. If you need the bytes gone from disk, this is not that.
- **`retain_until` is a marker, not a policy.** The field is recorded but nothing enforces it
  yet; an expired event is still visible. Track it or set it, but do not rely on it.
- **Retrieval is keyword overlap.** Deliberately simple and deterministic. No embeddings.
- **The demo's model call is a cloud call.** The memory is local; recalled text sent to
  OpenRouter is not.

More in [limitations](https://docs.humem.ai/audit-ready-memory/latest/guide/limitations/).

## Documentation

<https://docs.humem.ai/audit-ready-memory/latest/>

## Development

```bash
uv sync --all-groups --all-extras
uv run pytest
```

## License

MIT. See [LICENSE](LICENSE).
