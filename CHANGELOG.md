# Changelog

All notable changes to this project. Versions are the tags of this repository.

## Unreleased

### Breaking

- The memory is stored as a graph. A database written by 0.0.2 or earlier raises `ValueError` when
  opened. There is no migration.
- Requires the `arcadedb` package and Python 3.11 or newer, where 0.0.2 used `arcadedb-embedded`.

### Added

- `retain_until` is enforced: recalls and the assistant skip expired content, and
  `Memory.expire()` records the removal.
- `Memory.query()` runs read-only Cypher over the memory graph, with `NEXT`, `RECALLED`, and
  `DELETED` edges.
- A benchmark set with a documented input and output: `python -m benchmarks.run`.
- The demo can be hosted with sign-in, one memory per account, and limits. It gained example data,
  keep times, and a view of why an item was read or removed.
- Walkthroughs, templates, and guides on privacy, adoption, and reuse.

### Fixed

- Deleting an item a second time no longer changes which deletion is reported as having removed it.

## 0.0.2, 14 August 2026

- First release with the library: the append-only event log, deterministic replay, tombstone
  deletion, keyword retrieval, the optional assistant, and the local demo.

## 0.0.1, 4 June 2026

- Placeholder package. It contained no implementation.
