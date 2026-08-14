# Limitations

What this library does not do. Stated up front, because a project about auditability that
overstates itself has failed on its own terms.

## Deletion does not erase

Deletion is a tombstone. Content is excluded from every read path but stays in the
append-only log and remains retrievable with `get()`. If you need bytes gone from disk, see
the strategies in [retention and deletion](retention-and-deletion.md).

## `retain_until` does nothing yet

The field is recorded on messages and documents; no component reads it. Expired events remain
visible and searchable. Sweep it yourself, or do not rely on it.

## The log is not tamper-evident

Events are totally ordered by `seq`, but the log is not hash-chained and not signed. Anyone
who can write to the database file can rewrite history without leaving evidence. The
guarantees are against accidental mutation and application-level overwrites, not against a
motivated operator. Hash chaining is a plausible extension and is not implemented.

## No encryption at rest

The database is plain content in a local directory. Protect it with file permissions and
disk encryption at the deployment level.

## Retrieval is keyword overlap

`search()` scores lowercase word-overlap between the query and each item. It has no notion of
synonyms, morphology, or meaning: a query for "pumps" will not match "pump". This is a
deliberate choice. It is deterministic and explainable, which suits an audit trail, and
embeddings can be layered on later. It is not a competitive retrieval system.

## Replay covers the memory, not the model

The same log always produces the same state and therefore the same context. What a language
model does with that context is not reproducible, and nothing here makes it so.

## Single process, single writer

The store assigns `seq` from an in-process counter initialized at open. Two `Memory` objects
writing to one database concurrently will collide. Treat it as one writer at a time.

## Reads scale linearly

`replay()` folds the entire log on every call, and `search()` scans all visible content. Both
are O(n) in log length. This is fine at the scale the demo targets and will not stay fine at
millions of events; there is no incremental snapshot or index yet.

## The demo is a demo

`demo/app.py` simulates group members with no authentication, so anyone using it can act as
anyone and delete anything. Document parsing is deliberately shallow: text and markdown are
read raw, CSV and XLSX go through pandas' string rendering, PDFs through pypdf text
extraction, with no table structure or layout understanding. And the model call goes to
OpenRouter, so recalled text leaves the machine.

## Out of scope for now

Document understanding, vector search, multi-user synchronization and authorization, learned
retrieval policies, and a graph-structured episodic model. These belong to the wider HumemAI
roadmap rather than to this component.
