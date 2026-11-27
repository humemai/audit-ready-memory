"""Run the benchmark set and write JSON, CSV, and a result table.

    uv run python -m benchmarks.run                  # correctness checks
    uv run python -m benchmarks.run --performance    # and the timings

Exits with status 1 if any check or threshold fails.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from . import correctness, dataset, performance, reference

EXPECTED_FILE = Path(__file__).parent / "data" / f"expected-{dataset.SEED}.json"


def environment() -> dict:
    return {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "system": f"{platform.system()} {platform.machine()}",
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "arcadedb": version("arcadedb"),
        "audit_ready_memory": version("audit-ready-memory"),
        "dataset": dataset.DATA_FILE.name,
        "dataset_sha256": hashlib.sha256(dataset.DATA_FILE.read_bytes()).hexdigest(),
    }


def _table(rows: list[dict], columns: list[str]) -> str:
    def cell(value) -> str:
        if value is True:
            return "pass"
        if value is False:
            return "**FAIL**"
        return "" if value is None else str(value)

    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
        *("| " + " | ".join(cell(row[c]) for c in columns) + " |" for row in rows),
    ]
    return "\n".join(lines)


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(out: Path, results: dict) -> str:
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    _write_csv(out / "correctness.csv", results["correctness"])
    env = "\n".join(f"- {k}: `{v}`" for k, v in results["environment"].items())
    parts = [
        "# Benchmark results",
        env,
        "## Correctness",
        _table(results["correctness"], ["task", "check", "cases", "failures", "passed"]),
    ]
    if results["performance"]:
        _write_csv(out / "performance.csv", results["performance"])
        parts += [
            "## Performance",
            _table(
                results["performance"],
                ["events", "operation", "samples", "p50_ms", "p95_ms", "threshold_ms", "passed"],
            ),
        ]
    report = "\n\n".join(parts) + "\n"
    (out / "report.md").write_text(report)
    return report


def write_data() -> None:
    """Regenerate the committed input and its documented output."""
    operations = dataset.generate()
    dataset.DATA_FILE.write_text(dataset.dumps(operations), encoding="utf-8")
    documented = reference.expected(operations)
    EXPECTED_FILE.write_text(json.dumps(documented, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results/latest"))
    parser.add_argument("--performance", action="store_true")
    parser.add_argument("--sizes", type=int, nargs="+", default=[1_000, 10_000])
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--write-data", action="store_true", help="regenerate the input files")
    args = parser.parse_args(argv)
    if args.write_data:
        write_data()
        return 0

    operations = dataset.load()
    documented = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="arm-benchmark-") as tmp:
        checks = correctness.run(Path(tmp), operations, documented)
        timings = []
        if args.performance:
            for size in args.sizes:
                timings += performance.measure(Path(tmp), size, args.repeats)
    results = {"environment": environment(), "correctness": checks, "performance": timings}
    print(write_report(args.out, results))
    failed = [r for r in checks if not r["passed"]]
    failed += [r for r in timings if r["passed"] is False]
    for row in failed:
        print("FAILED:", row, file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
