# Audit-Ready Memory

A local-first memory layer for AI agents. Memory is a time-stamped log you can read, replay,
and delete from, rather than hidden state inside a model or a hosted service.

Events are appended to an embedded [ArcadeDB](https://arcadedb.com/) database and never
updated in place. Reads are recorded as well as writes, so the log answers the question an
audit actually asks: what did the system show the model, and when? Deletion is an appended
tombstone carrying a required reason, and deleted content cannot re-enter a model's context.

Funded by [SIDN Fund](https://www.sidnfonds.nl/).

## Start here

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md) builds a log, replays it, and deletes from it
- [Memory Model](guide/memory-model.md) covers the four event kinds and the invariants
- [API Reference](reference/api.md)

## What it gives you

- **A readable history.** Every write and every read is an event with an id, a UTC timestamp,
  and a store-assigned position in the log.
- **Reconstructable state.** `replay(up_to_seq=n)` rebuilds memory as it stood at any past
  point, by folding the log. The same log always gives the same state.
- **Auditable reads.** Retrieval and its audit record are produced in one step, so what the
  log says the model saw is what the model saw.
- **Deletion you can prove.** Removing content appends a tombstone with a reason and
  optionally who asked. The removal is itself part of the record.
- **No server.** The database is a local directory. Nothing leaves the machine unless you
  wire up a model that sends it.

## What it does not give you

Deletion excludes content from every read path but does not erase it from the log.
`retain_until` is recorded and not yet enforced. The log is ordered but not hash-chained, so
it resists accidents rather than a determined operator. Retrieval is keyword overlap, not
semantic search.

[Limitations](guide/limitations.md) covers all of this in full, and
[retention and deletion](guide/retention-and-deletion.md) explains what to do about it.

## Status

The library is implemented, tested, and published. 74 tests cover schema validation, replay
determinism, store behavior, deletion auditability, and persistence across reopen. Benchmarks
are in progress.

Version numbers are still below `0.1.0` on purpose. The API is usable but not yet frozen, so
pin an exact version if you depend on it.
