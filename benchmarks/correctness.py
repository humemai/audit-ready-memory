"""Pass or fail checks for consistency, replay, retention, and deletion."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from audit_ready_memory import (
    Assistant,
    Document,
    Memory,
    MemoryState,
    Message,
    event_from_dict,
    event_to_dict,
    replay,
    search,
)

from .dataset import FUTURE, START, content_id
from .reference import CHECKPOINT_EVERY, Reference, digest


class Checks:
    """Collects every case of every check, so a report shows how much was tested."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict] = {}

    def case(self, task: str, name: str, passed: bool, detail: object = "") -> None:
        row = self._rows.setdefault(
            (task, name),
            {"task": task, "check": name, "cases": 0, "failures": 0, "example": ""},
        )
        row["cases"] += 1
        if not passed:
            row["failures"] += 1
            row["example"] = row["example"] or str(detail)[:300]

    def results(self) -> list[dict]:
        return [{**row, "passed": row["failures"] == 0} for row in self._rows.values()]


def snapshot(state: MemoryState) -> dict:
    """The library's state in the same shape as ``Reference.snapshot``."""
    return {
        "events": 0 if state.last_seq is None else state.last_seq + 1,
        "messages": [str(m.id) for m in state.visible_messages],
        "documents": [str(d.id) for d in state.visible_documents],
        "deleted": {str(key): value.seq for key, value in state.deleted.items()},
        "reads": {str(k): v.num_recalled for k, v in state.recall_stats.items()},
    }


def _apply(memory: Memory, index: int, op: dict) -> list[str] | None:
    """Do one operation through the library's public API."""
    kind = op["op"]
    if kind in ("message", "document"):
        until = op["retain_until"]
        common = {
            "id": content_id(op["ref"]),
            "timestamp": START + timedelta(minutes=index),
            "retain_until": datetime.fromisoformat(until) if until else None,
        }
        if kind == "message":
            memory.add_message(
                Message(
                    speaker=op["speaker"],
                    content=op["text"],
                    session_id=op["session"],
                    **common,
                )
            )
        else:
            memory.add_document(Document(name=op["name"], text=op["text"], **common))
        return None
    if kind == "recall":
        _, items = memory.recall(op["query"])
        return [str(item.id) for item in items]
    if kind == "delete":
        deletion = memory.delete(
            tuple(content_id(ref) for ref in op["refs"]), reason=op["reason"]
        )
        return [str(target) for target in deletion.targets]
    deletion = memory.expire(as_of=datetime.fromisoformat(op["as_of"]))
    return None if deletion is None else [str(target) for target in deletion.targets]


def _edges(memory: Memory, edge: str) -> set[tuple[int, int]]:
    rows = memory.query(
        f"MATCH (a:MemoryEvent)-[:{edge}]->(b:MemoryEvent) "
        "RETURN a.seq AS source, b.seq AS target"
    )
    return {(row["source"], row["target"]) for row in rows}


def _run_operations(
    memory: Memory, operations: list[dict], checks: Checks
) -> tuple[Reference, list[tuple[int, dict]]]:
    reference = Reference()
    checkpoints = []
    for index, op in enumerate(operations):
        got = _apply(memory, index, op)
        want = reference.apply(op)
        if op["op"] == "recall":
            checks.case(
                "consistency", "each recall returns the expected items in order",
                got == want, (index, got, want),
            )
        elif op["op"] == "expire":
            checks.case(
                "retention", "each sweep deletes exactly what was due",
                got == want, (index, got, want),
            )
        checks.case(
            "consistency", "the log has the expected number of events",
            len(memory) == reference.size, (index, len(memory), reference.size),
        )
        if (index + 1) % CHECKPOINT_EVERY == 0 or index == len(operations) - 1:
            wanted = reference.snapshot()
            got_state = snapshot(memory.replay())
            checks.case(
                "consistency", "replayed state matches the reference",
                got_state == wanted, index,
            )
            checkpoints.append((reference.size - 1, wanted))
    seqs = [event.seq for event in memory.events()]
    checks.case(
        "consistency", "seq is gapless and increasing",
        seqs == list(range(reference.size)), seqs[:10],
    )
    for edge, wanted_edges in (
        ("NEXT", reference.next_edges),
        ("RECALLED", reference.recalled_edges),
        ("DELETED", reference.deleted_edges),
    ):
        got_edges = _edges(memory, edge)
        checks.case(
            "consistency", f"{edge} edges match the reference",
            got_edges == wanted_edges, sorted(got_edges ^ wanted_edges)[:5],
        )
    return reference, checkpoints


def _check_replay(
    memory: Memory,
    checkpoints: list[tuple[int, dict]],
    expected: dict,
    checks: Checks,
) -> None:
    for (last_seq, wanted), documented in zip(checkpoints, expected["checkpoints"]):
        state = memory.replay(up_to_seq=last_seq)
        checks.case(
            "replay", "a past point replays to the state it had then",
            snapshot(state) == wanted, last_seq,
        )
        checks.case(
            "replay", "state matches the documented output",
            digest(snapshot(state)) == documented["digest"]
            and last_seq == documented["last_seq"],
            last_seq,
        )
    checks.case(
        "replay", "one documented output per checkpoint",
        len(checkpoints) == len(expected["checkpoints"]),
        (len(checkpoints), len(expected["checkpoints"])),
    )
    full = memory.replay()
    checks.case("replay", "replaying twice gives the same state", memory.replay() == full)
    exported = [json.dumps(event_to_dict(event)) for event in memory.events()]
    rebuilt = replay(event_from_dict(json.loads(line)) for line in exported)
    checks.case("replay", "the exported log rebuilds the same state", rebuilt == full)


def _check_retention(memory: Memory, reference: Reference, checks: Checks) -> None:
    dated = [i for i in reference.items.values() if i["retain_until"] is not None]
    overdue = {i["id"] for i in dated if i["retain_until"] < FUTURE}
    for event in memory.events(kind="recall"):
        leaked = overdue & {str(item) for item in event.recalled}
        checks.case(
            "retention", "no recall includes expired content",
            not leaked, (event.seq, leaked),
        )
    swept = memory.expire()
    if swept is not None:
        # the deletion checks below cover what this last sweep removed, too
        by_id = {item["id"]: item for item in reference.items.values()}
        for target in swept.targets:
            item = by_id[str(target)]
            if item["deleted_seq"] is None:
                item["deleted_seq"] = swept.seq
    state = memory.replay()
    visible = {str(i.id) for i in (*state.visible_messages, *state.visible_documents)}
    checks.case(
        "retention", "after a sweep nothing expired is visible",
        not overdue & visible, overdue & visible,
    )
    for item in dated:
        if item["retain_until"] == FUTURE and item["deleted_seq"] is None:
            checks.case(
                "retention", "content that has not expired survives a sweep",
                item["id"] in visible, item["id"],
            )
    size = len(memory)
    checks.case(
        "retention", "a second sweep writes nothing",
        memory.expire() is None and len(memory) == size,
    )


def _check_deletion(memory: Memory, reference: Reference, checks: Checks) -> None:
    removed = [i for i in reference.items.values() if i["deleted_seq"] is not None]
    state = memory.replay()
    visible = {str(i.id) for i in (*state.visible_messages, *state.visible_documents)}
    recalls = memory.events(kind="recall")
    tombstones = {str(k): v for k, v in state.deleted.items()}
    for item in removed:
        key = item["id"]
        marker = item["secret"].replace("secret", "item")
        checks.case("deletion", "deleted content is not visible", key not in visible, key)
        checks.case(
            "deletion", "search cannot find deleted content",
            key not in {str(hit.id) for hit in search(state, marker, limit=50)}, key,
        )
        checks.case(
            "deletion", "no later recall includes it",
            not any(
                key in {str(target) for target in event.recalled}
                for event in recalls
                if event.seq > item["deleted_seq"]
            ),
            key,
        )
        tombstone = tombstones.get(key)
        checks.case(
            "deletion", "the log names when and why it was removed",
            tombstone is not None
            and tombstone.seq == item["deleted_seq"]
            and bool(tombstone.reason),
            key,
        )
        checks.case(
            "deletion", "the original stays in the log (a tombstone, not erasure)",
            memory.get(key) is not None, key,
        )

    # What would actually be sent to a model, captured by a stand-in client.
    sent: list[str] = []

    def create(*, model, messages):
        sent.append(messages[-1]["content"])
        answer = SimpleNamespace(content="noted")
        return SimpleNamespace(choices=[SimpleNamespace(message=answer)])

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    assistant = Assistant(memory, client=client)
    for item in removed:
        marker = item["secret"].replace("secret", "item")
        assistant.reply(f"what about {marker}", speaker="coordinator")
        checks.case(
            "deletion", "deleted content never reaches the model's context",
            item["secret"] not in sent[-1], item["id"],
        )


def run(directory: Path, operations: list[dict], expected: dict) -> list[dict]:
    """Run every correctness check in a new database under ``directory``."""
    checks = Checks()
    path = Path(directory) / "correctness-db"
    with Memory(path) as memory:
        reference, checkpoints = _run_operations(memory, operations, checks)
        _check_replay(memory, checkpoints, expected, checks)
        before = memory.replay()
    with Memory(path) as memory:
        checks.case(
            "replay", "reopening the database gives the same state",
            memory.replay() == before,
        )
        # These two write to the log, so they come last.
        _check_retention(memory, reference, checks)
        _check_deletion(memory, reference, checks)
    return checks.results()
