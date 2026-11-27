"""Export the audit log to CSV, without the content of messages and documents.

Run from a clone: uv run python examples/export_audit_log.py [path/to/memory]
Without a path it builds a small example memory first.
"""

import csv
import sys
import tempfile

from audit_ready_memory import Deletion, Memory, Message, Recall

COLUMNS = ("seq", "timestamp", "kind", "session", "who", "items", "reason")


def rows(memory: Memory):
    """One row per event. Item numbers stand in for content, so the export holds none."""
    seq_of = {event.id: event.seq for event in memory.events()}
    for event in memory.events():
        items, reason = (), ""
        who = event.actor or ""
        if isinstance(event, Message):
            who = event.speaker
        elif isinstance(event, Recall):
            items = event.recalled
        elif isinstance(event, Deletion):
            items, reason = event.targets, event.reason
            who = event.requested_by or who
        yield {
            "seq": event.seq,
            "timestamp": event.timestamp.isoformat(timespec="seconds"),
            "kind": event.kind,
            "session": event.session_id or "",
            "who": who,
            "items": " ".join(str(seq_of[item]) for item in items),
            "reason": reason,
        }


def export(memory: Memory, handle) -> None:
    writer = csv.DictWriter(handle, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows(memory))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        with Memory(sys.argv[1]) as memory:
            export(memory, sys.stdout)
    else:
        with tempfile.TemporaryDirectory() as folder:
            with Memory(f"{folder}/memory") as memory:
                note = memory.add_message(
                    Message(speaker="resident-a", content="private detail")
                )
                memory.recall("detail", actor="assistant")
                memory.delete((note.id,), reason="asked to remove", requested_by="a")
                export(memory, sys.stdout)
