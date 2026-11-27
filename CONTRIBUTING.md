# Contributing

Reports and changes are welcome, also from people who do not write code. For feedback, use the
[feedback form](https://github.com/humemai/audit-ready-memory/issues/new?template=feedback.yml).

## Set up and check

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
bash scripts/verify.sh
```

That installs everything with `uv`, runs the tests and the benchmark set, and runs the examples.
Continuous integration runs the same script.

## A change, step by step

1. Open an issue that describes the problem.
2. Work on a branch.
3. Add a test that fails without your change.
4. Update the documentation and `CHANGELOG.md` in the same pull request.
5. Run `bash scripts/verify.sh`.
6. Open a pull request that says `Closes #<issue>`.

## Rules that must keep holding

- The store only appends. It never updates or removes an event.
- Replay depends only on the events and their `seq`, never on the clock.
- Anything a model is shown is recorded as a recall before it is sent.
- Deleted or expired content is never recalled.

The [invariants](docs/guide/memory-model.md#invariants) and the
[benchmark set](docs/guide/benchmarks.md) check these.

## Maintenance and upgrades

| Task | How |
|---|---|
| Update dependencies | `uv lock --upgrade`, then `bash scripts/verify.sh` |
| New database engine version | The same, and read the engine's release notes for storage changes |
| Change the storage layout | Refuse old databases with a clear error or migrate them, and note it under "Breaking" in the changelog |
| Change the benchmark input | `uv run python -m benchmarks.run --write-data`, and explain the change |
| Release | See the [release workflow](docs/development/release.md) |
