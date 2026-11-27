# Templates

Copy these into your own project documentation and fill them in.

## Retention rules

| Kind of entry | Example | Keep for | `retain_until` set by | Why this long |
|---|---|---|---|---|
| Reports about public space | "The pump is broken" | 1 year | The application, on writing | Follow-up and yearly review |
| Contact details | A phone number | 30 days | The application, on writing | Only needed to arrange the visit |
| Access codes and passwords | A gate code | Do not store | | Cannot be erased entry by entry |
| Uploaded documents | An inspection report | | | |

- `expire()` runs: *(for example every night)*
- Run by: *(person or job)*
- Checked by: *(person)*, every: *(period)*

## Record of data sources

| Source | What comes in | Personal data? | Lawful basis | Keep time | Owner |
|---|---|---|---|---|---|
| Residents' messages | Free text | Possibly | | | |
| Staff uploads | Reports | | | | |

## Removal requests

| Received | From | Event numbers | Reason entered | Done by | Deletion event | Erasure needed? | Answered |
|---|---|---|---|---|---|---|---|
| | | | | | | | |

Carry out a request with:

```python
deletion = memory.delete(ids, reason="request of 3 December", requested_by="resident-a")
print(deletion.seq)  # the number to write in the table
```

## Audit log export

[`examples/export_audit_log.py`](https://github.com/humemai/audit-ready-memory/blob/main/examples/export_audit_log.py)
writes one row per event to CSV: number, time, kind, session, who, the numbers of the items read or
removed, and the reason. It leaves out the content of messages and documents, so the export can be
shared more widely than the memory itself.

```bash
uv run python examples/export_audit_log.py path/to/memory > audit-log.csv
```

Check the reasons and the names in the export before sharing it.
