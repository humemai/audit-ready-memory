"""What the memory should contain, worked out without the library.

This is a second, deliberately plain implementation of the rules in the documentation. It
imports nothing from ``audit_ready_memory``, so agreement between the two means something.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from .dataset import FUTURE, content_id

CHECKPOINT_EVERY = 25
RECALL_LIMIT = 5


def digest(snapshot: dict) -> str:
    text = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def _words(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"\w+", text)}


class Reference:
    def __init__(self) -> None:
        self.items: dict[int, dict] = {}  # by operation ref, in log order
        self.size = 0  # events in the log, which is also the next seq
        self.next_edges: set[tuple[int, int]] = set()
        self.recalled_edges: set[tuple[int, int]] = set()
        self.deleted_edges: set[tuple[int, int]] = set()
        self._last_message: dict[str | None, int] = {}

    def apply(self, op: dict) -> list[str] | None:
        """Apply one operation. Returns the ids a recall or an expiry should name."""
        kind = op["op"]
        if kind in ("message", "document"):
            return self._write(op)
        if kind == "recall":
            return self._recall(op["query"])
        if kind == "delete":
            return self._delete([self.items[ref] for ref in op["refs"]])
        as_of = datetime.fromisoformat(op["as_of"])
        due = [
            item
            for item in self.items.values()
            if item["deleted_seq"] is None
            and item["retain_until"] is not None
            and item["retain_until"] <= as_of
        ]
        return self._delete(due) if due else None

    def _write(self, op: dict) -> None:
        who = op["speaker"] if op["op"] == "message" else op["name"]
        until = op["retain_until"]
        self.items[op["ref"]] = {
            "id": str(content_id(op["ref"])),
            "seq": self.size,
            "kind": op["op"],
            "words": _words(f"{who} {op['text']}"),
            "secret": f"secret{op['ref']:05d}",
            "retain_until": datetime.fromisoformat(until) if until else None,
            "deleted_seq": None,
            "reads": 0,
        }
        if op["op"] == "message":
            previous = self._last_message.get(op["session"])
            if previous is not None:
                self.next_edges.add((previous, self.size))
            self._last_message[op["session"]] = self.size
        self.size += 1

    def _recall(self, query: str) -> list[str]:
        wanted = _words(query)
        found = []
        for item in self.items.values():
            until = item["retain_until"]
            expired = until is not None and until < FUTURE
            overlap = len(wanted & item["words"])
            if overlap and item["deleted_seq"] is None and not expired:
                found.append((-overlap, item["seq"], item))
        found.sort(key=lambda entry: entry[:2])
        hits = [entry[2] for entry in found[:RECALL_LIMIT]]
        for item in hits:
            item["reads"] += 1
            self.recalled_edges.add((self.size, item["seq"]))
        self.size += 1
        return [item["id"] for item in hits]

    def _delete(self, items: list[dict]) -> list[str]:
        for item in items:
            self.deleted_edges.add((self.size, item["seq"]))
            if item["deleted_seq"] is None:
                item["deleted_seq"] = self.size
        self.size += 1
        return [item["id"] for item in items]

    def snapshot(self) -> dict:
        items = self.items.values()
        visible = [item for item in items if item["deleted_seq"] is None]
        return {
            "events": self.size,
            "messages": [i["id"] for i in visible if i["kind"] == "message"],
            "documents": [i["id"] for i in visible if i["kind"] == "document"],
            "deleted": {
                i["id"]: i["deleted_seq"] for i in items if i["deleted_seq"] is not None
            },
            "reads": {i["id"]: i["reads"] for i in items if i["reads"]},
        }


def expected(operations: list[dict]) -> dict:
    """The documented output for an input: a digest of the state at each checkpoint."""
    reference = Reference()
    checkpoints = []
    for index, op in enumerate(operations):
        reference.apply(op)
        if (index + 1) % CHECKPOINT_EVERY == 0 or index == len(operations) - 1:
            checkpoints.append(
                {
                    "after_operation": index + 1,
                    "last_seq": reference.size - 1,
                    "digest": digest(reference.snapshot()),
                }
            )
    state = reference.snapshot()
    return {
        "operations": len(operations),
        "events": state["events"],
        "visible_messages": len(state["messages"]),
        "visible_documents": len(state["documents"]),
        "deleted_items": len(state["deleted"]),
        "checkpoints": checkpoints,
    }
