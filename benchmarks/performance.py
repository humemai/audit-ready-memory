"""How long the everyday operations take as the log grows.

The thresholds were written down on 2026-11-27, before the first measurement. They ask
whether the memory is usable behind an interactive assistant on a modest machine, not how
it compares with anything else.
"""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from pathlib import Path

from audit_ready_memory import Document, Memory, Message, Recall

# milliseconds, compared with the 95th percentile
THRESHOLDS = {
    1_000: {"append": 50, "replay": 500, "recall": 750, "query": 500, "open": 10_000},
    10_000: {"append": 50, "replay": 2_000, "recall": 2_500, "query": 500, "open": 10_000},
}

_THINGS = ("pump", "streetlight", "bench", "drain", "gate", "bin")


def percentile(values: list[float], share: float) -> float:
    """Nearest-rank percentile: a value that was actually measured."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def _timed(samples: list[float], step):
    start = time.perf_counter()
    result = step()
    samples.append((time.perf_counter() - start) * 1000)
    return result


def _event(index: int):
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    text = f"item{index} {_THINGS[index % len(_THINGS)]} reported on the north side"
    if index % 20 == 0:
        return Document(name=f"report-{index}.txt", text=text * 5, timestamp=when)
    return Message(speaker="resident", content=text, timestamp=when, session_id="a")


def measure(directory: Path, size: int, repeats: int = 20) -> list[dict]:
    """Fill a new log with ``size`` events and time each operation."""
    path = Path(directory) / f"performance-{size}"
    samples: dict[str, list[float]] = {name: [] for name in THRESHOLDS[1_000]}
    with Memory(path) as memory:
        content = []
        for index in range(size):
            if content and index % 25 == 24:
                memory.delete((content[index % len(content)],), reason="benchmark")
                continue
            if content and index % 10 == 9:
                memory.record_recall(Recall(query="q", recalled=(content[-1],)))
                continue
            event = _event(index)
            add = memory.add_document if event.kind == "document" else memory.add_message
            content.append(_timed(samples["append"], lambda: add(event)).id)
        probe = {"id": str(content[-1])}
        for _ in range(repeats):
            _timed(samples["replay"], memory.replay)
            _timed(samples["recall"], lambda: memory.recall("pump north"))
            _timed(
                samples["query"],
                lambda: memory.query(
                    "MATCH (r:Recall)-[:RECALLED]->(m:MemoryEvent {id: $id}) "
                    "RETURN r.seq AS seq",
                    probe,
                ),
            )
    # reopening in a process that already has the database engine loaded
    for _ in range(min(repeats, 5)):
        _timed(samples["open"], lambda: Memory(path)).close()

    limits = THRESHOLDS.get(size, {})
    rows = []
    for name, values in samples.items():
        p95 = percentile(values, 0.95)
        limit = limits.get(name)
        rows.append(
            {
                "events": size,
                "operation": name,
                "samples": len(values),
                "p50_ms": round(percentile(values, 0.5), 2),
                "p95_ms": round(p95, 2),
                "threshold_ms": limit,
                "passed": None if limit is None else p95 <= limit,
            }
        )
    return rows
