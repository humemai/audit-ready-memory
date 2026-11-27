# Adoption guide

For a team deciding whether to try this, for example in a municipality, a civic technology group,
an NGO, or a research project.

## Use it when

- You need to show later what an AI system was given, and why.
- Removal requests must leave a record: what was removed, when, why, and at whose request.
- The memory has to stay on a machine you control.
- A small, readable code base matters more to you than search quality or scale.

## Do not use it when

- Data must be erased from disk entry by entry. Deletion here hides, it does not erase.
- You need to prove nobody altered the log. It is not signed or hash-chained.
- Several processes must write at the same time.
- You need search that understands meaning. Search compares words.
- The log will grow to millions of events. Reads fold the whole log.
- You need user accounts and permissions. The library has none.

## Checklist for a local pilot

- [ ] Write down the purpose, and which data you will put in. Use made-up data for the first round.
- [ ] Name who may read the memory folder, and who may delete from it.
- [ ] Choose keep times per kind of data, using the [retention template](templates.md#retention-rules).
- [ ] Decide how often `expire()` runs, and who checks that it ran.
- [ ] Decide how a removal request reaches you and who carries it out.
- [ ] Decide what you will do if something must be erased, not only hidden.
- [ ] Decide whether text may leave the machine. If not, point the assistant at a local model.
- [ ] Back up the memory folder, or decide not to. A backup also keeps deleted entries.
- [ ] Ask your privacy officer whether an impact assessment is needed.
- [ ] Agree when the pilot ends and what happens to the folder then.

## Checklist for installing safely

- [ ] Python 3.11 or newer, and `uv`.
- [ ] `uv add audit-ready-memory` in a project of your own.
- [ ] The memory folder outside any web server's public folder and any shared drive.
- [ ] File permissions that allow only the account running your service.
- [ ] Disk encryption on the machine.
- [ ] A model key, if used, in an environment variable with a spending limit, never in code.

## First-time users

1. Run the [demo](demo.md) and load an example.
2. Follow the two [walkthroughs](walkthroughs.md).
3. Read [limitations](limitations.md) before putting in real data.

## Common pitfalls

| Pitfall | What happens | Instead |
|---|---|---|
| Treating `delete()` as erasure | The text is still on disk and `get()` returns it | Keep erasable data outside the log |
| Setting `retain_until` and never calling `expire()` | Nothing records the removal | Schedule `expire()` |
| Feeding `query()` results to a model | Deleted and expired content reaches it | Use `recall()` for anything a model sees |
| Adding items to a model's context without a recall | The log no longer shows what was seen | Record every read with `recall()` or `record_recall()` |
| Opening one memory from two processes | Writes collide | One writer per memory |

## Tell me how it went

Open a [feedback issue](https://github.com/humemai/audit-ready-memory/issues/new?template=feedback.yml)
or write to info@humem.ai. No technical knowledge is needed.
