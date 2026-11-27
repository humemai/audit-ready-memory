"""The benchmark input: a fixed list of operations on a made-up neighbourhood log.

Residents report broken pumps and streetlights, upload reports, search the memory, ask for
things to be removed, and let some entries expire. There is no personal data: speakers are
roles and every sentence is generated.

Everything is derived from one seed through ``random.Random(seed).random()``, the one call
Python guarantees to give the same sequence in every version. The committed file in
``benchmarks/data`` is the documented input, and ``generate`` must reproduce it exactly.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

SEED = 261009
SIZE = 300
DATA_FILE = Path(__file__).parent / "data" / f"neighbourhood-{SEED}.jsonl"

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
# Retention times lie well in the past or far in the future, so that results do not
# depend on the day the benchmark runs.
PAST = tuple(datetime(2026, month, 1, tzinfo=timezone.utc) for month in (2, 3, 4))
FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)

SPEAKERS = ("resident-a", "resident-b", "resident-c", "coordinator")
SESSIONS = ("north-street", "south-street", None)
THINGS = ("pump", "streetlight", "bench", "drain", "gate", "bin", "crossing", "playground")
STATES = (
    "broken",
    "repaired",
    "leaking",
    "blocked",
    "checked",
    "missing",
    "reported",
    "replaced",
)
REASONS = (
    "resident asked for removal",
    "entered by mistake",
    "contains a private detail",
)


def content_id(ref: int, seed: int = SEED) -> UUID:
    """The fixed id of the message or document created by operation ``ref``."""
    return uuid5(NAMESPACE_URL, f"audit-ready-memory/benchmark/{seed}/{ref}")


def generate(seed: int = SEED, size: int = SIZE) -> list[dict]:
    """Return ``size`` operations. The same arguments always give the same list."""
    rng = random.Random(seed)

    def pick(options):
        return options[int(rng.random() * len(options))]

    def retention() -> str | None:
        draw = rng.random()
        if draw < 0.15:
            return pick(PAST).isoformat()
        if draw < 0.25:
            return FUTURE.isoformat()
        return None

    # three expiry sweeps, in time order, spread through the run
    sweeps = {int(size * at): PAST[i] for i, at in enumerate((0.4, 0.65, 0.9))}
    operations: list[dict] = []
    content: list[int] = []
    for ref in range(size):
        if ref in sweeps:
            operations.append({"op": "expire", "as_of": sweeps[ref].isoformat()})
            continue
        draw = 0.0 if ref < 10 else rng.random()
        # marker: findable by search. secret: appears only inside this item's text.
        words = f"item{ref:05d} {pick(THINGS)} {pick(STATES)} secret{ref:05d}"
        if draw < 0.55:
            operations.append(
                {
                    "op": "message",
                    "ref": ref,
                    "speaker": pick(SPEAKERS),
                    "text": words,
                    "session": pick(SESSIONS),
                    "retain_until": retention(),
                }
            )
            content.append(ref)
        elif draw < 0.65:
            operations.append(
                {
                    "op": "document",
                    "ref": ref,
                    "name": f"report-{ref:05d}.txt",
                    "text": f"{words} {pick(THINGS)} {pick(STATES)}",
                    "retain_until": retention(),
                }
            )
            content.append(ref)
        elif draw < 0.9:
            if rng.random() < 0.4:
                query = f"item{pick(content):05d}"
            else:
                query = f"{pick(THINGS)} {pick(STATES)}"
            operations.append({"op": "recall", "query": query})
        else:
            targets = [pick(content)]
            if rng.random() < 0.3:
                targets.append(pick(content))
            operations.append(
                {
                    "op": "delete",
                    "refs": list(dict.fromkeys(targets)),
                    "reason": pick(REASONS),
                }
            )
    return operations


def dumps(operations: list[dict]) -> str:
    return "".join(json.dumps(op, sort_keys=True) + "\n" for op in operations)


def load(path: Path = DATA_FILE) -> list[dict]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]
