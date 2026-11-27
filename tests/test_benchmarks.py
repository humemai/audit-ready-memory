"""The benchmark set stays reproducible, passes, and can actually fail."""

import json

import pytest

from audit_ready_memory import Memory, search
from audit_ready_memory import store as store_module
from benchmarks import correctness, dataset, performance, reference, run


@pytest.fixture(scope="module")
def operations():
    return dataset.load()


@pytest.fixture(scope="module")
def documented():
    return json.loads(run.EXPECTED_FILE.read_text(encoding="utf-8"))


def _failed(results):
    return {(row["task"], row["check"]) for row in results if not row["passed"]}


class TestInputsAndOutputs:
    def test_generator_reproduces_the_committed_input(self):
        committed = dataset.DATA_FILE.read_text(encoding="utf-8")
        assert dataset.dumps(dataset.generate()) == committed

    def test_reference_reproduces_the_documented_output(self, operations, documented):
        assert reference.expected(operations) == documented

    def test_input_exercises_every_operation(self, operations, documented):
        kinds = {op["op"] for op in operations}
        assert kinds == {"message", "document", "recall", "delete", "expire"}
        assert documented["deleted_items"] > 10


class TestCorrectness:
    def test_every_check_passes(self, tmp_path, operations, documented):
        results = correctness.run(tmp_path, operations, documented)
        assert _failed(results) == set()
        assert {row["task"] for row in results} == {
            "consistency",
            "replay",
            "retention",
            "deletion",
        }

    def test_ignoring_retention_is_caught(
        self, tmp_path, monkeypatch, operations, documented
    ):
        monkeypatch.setattr(
            store_module,
            "search",
            lambda state, query, limit=5, as_of=None: search(state, query, limit=limit),
        )
        failed = _failed(correctness.run(tmp_path, operations, documented))
        assert ("retention", "no recall includes expired content") in failed

    def test_a_sweep_that_does_nothing_is_caught(
        self, tmp_path, monkeypatch, operations, documented
    ):
        monkeypatch.setattr(Memory, "expire", lambda self, **kwargs: None)
        failed = _failed(correctness.run(tmp_path, operations, documented))
        assert ("retention", "each sweep deletes exactly what was due") in failed


class TestPerformance:
    def test_measures_every_operation(self, tmp_path):
        rows = performance.measure(tmp_path, size=60, repeats=2)
        assert [row["operation"] for row in rows] == [
            "append",
            "replay",
            "recall",
            "query",
            "open",
        ]
        # no threshold applies to this tiny size, so nothing here depends on the machine
        assert all(row["passed"] is None and row["samples"] for row in rows)

    def test_percentile_is_a_measured_value(self):
        values = [float(n) for n in range(1, 21)]
        assert performance.percentile(values, 0.5) == 10
        assert performance.percentile(values, 0.95) == 19


class TestReport:
    def test_writes_json_csv_and_table(self, tmp_path):
        assert run.main(["--out", str(tmp_path / "out")]) == 0
        written = sorted(path.name for path in (tmp_path / "out").iterdir())
        assert written == ["correctness.csv", "report.md", "results.json"]
