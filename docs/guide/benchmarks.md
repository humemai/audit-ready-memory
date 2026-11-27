# Benchmarks

A set of checks that anyone can run to see whether the memory does what these pages say: with a
documented input, a documented output, and a pass or fail for each rule.

## Run it

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
uv sync
uv run python -m benchmarks.run
```

It writes `results.json`, `correctness.csv`, and `report.md` to `benchmarks/results/latest/` and
exits with status 1 if anything fails. Add `--performance` for the timings, which also writes
`performance.csv`. `--out` chooses another folder.

## The input

[`benchmarks/data/neighbourhood-261009.jsonl`](https://github.com/humemai/audit-ready-memory/blob/main/benchmarks/data/neighbourhood-261009.jsonl)
holds 300 operations on a made-up neighbourhood log: residents report broken pumps and
streetlights, upload reports, search the memory, ask for entries to be removed, and let some expire.
There is no personal data.

| Operation | Count |
|---|---|
| `message` | 187 |
| `document` | 24 |
| `recall` | 56 |
| `delete` | 30 |
| `expire` | 3 |

One line of each of four kinds:

```json
{"op": "message", "ref": 0, "retain_until": "2026-04-01T00:00:00+00:00", "session": "south-street", "speaker": "resident-c", "text": "item00000 bench repaired secret00000"}
{"op": "recall", "query": "item00003"}
{"op": "delete", "reason": "entered by mistake", "refs": [25]}
{"as_of": "2026-02-01T00:00:00+00:00", "op": "expire"}
```

`benchmarks/dataset.py` regenerates the file from the seed 261009, and a test checks that it
still matches.

## The expected output

`benchmarks/data/expected-261009.json` holds a SHA-256 digest of the memory state after every
25 operations (12 checkpoints). A state is the
number of events, the visible messages and documents in order, each deleted item with the `seq` of
the deletion that removed it, and how often each item was recalled. The final state has
300 events, 130 visible messages,
21 visible documents, and 60 deleted items.

The digests come from `benchmarks/reference.py`, a second, plain implementation of the rules that
imports nothing from the library.

## Correctness

A check passes when none of its cases fails.

| Task | What is checked |
|---|---|
| Consistency | Every recall returns the expected items in order; the replayed state matches the reference; `seq` has no gaps; the `NEXT`, `RECALLED`, and `DELETED` edges are exactly the expected ones |
| Replay | Every past point replays to the state it had then and to the documented digest; replaying twice, reopening the database, and rebuilding from the exported log give the same state |
| Retention | Each sweep deletes exactly what was due; no recall ever includes expired content; unexpired content survives; a second sweep writes nothing |
| Deletion | Deleted content is not visible, not found by search, not recalled later, and not in the text sent to a model; the log says when and why it went; the original stays in the log |

## Performance

The figure compared with each threshold is the 95th percentile.

| Name | Operation | 1,000 events | 10,000 events |
|---|---|---|---|
| `append` | write one event | 50 ms | 50 ms |
| `replay` | `replay()` of the whole log | 500 ms | 2,000 ms |
| `recall` | `recall()`: search and record the read | 750 ms | 2,500 ms |
| `query` | one Cypher query: the recalls of an item | 500 ms | 500 ms |
| `open` | reopen the database, engine already loaded | 10,000 ms | 10,000 ms |

These thresholds were written down on 27 November 2026, before the first measurement. They ask
whether the memory is usable behind an interactive assistant on a modest machine. They do not compare
it with other systems. No timings are published yet.

## What this does not show

- One made-up scenario of 300 operations shows that the rules hold on this input, not on
  every input.
- The reference was written by the same author as the library, so a shared misunderstanding of a rule
  would pass.
- One process writes at a time. Concurrent writers are not supported and not tested.
- The deletion checks show that content is no longer read. They do not show erasure, which the
  library does not do.
- Timings depend on the machine they run on.
