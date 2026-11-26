"""Tests for the benchmark harness itself: a crashed task must not end the run."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "eval"))

import run_bench  # noqa: E402
from tasks import TASKS  # noqa: E402


def test_a_crashed_task_is_recorded_instead_of_killing_the_run(monkeypatch):
    def boom(task, keep=False, model=None):
        raise TimeoutError("timed out")

    monkeypatch.setattr(run_bench, "run_task", boom)
    row = run_bench.run_task_safely(TASKS[0], retries=1)
    assert row["id"] == "a01"
    assert row["status"] == "harness_error"
    assert row["success"] is False
    assert "TimeoutError" in row["errors"][0]["error"]
    # The summary still has to work with a row that never ran.
    summary = run_bench.summarize([row], 1.0)
    assert summary["tasks"] == 1
    assert summary["success"] == 0


def test_one_retry_is_enough_when_the_second_attempt_works(monkeypatch):
    attempts = {"n": 0}

    def flaky(task, keep=False, model=None):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TimeoutError("timed out")
        return {"id": task["id"], "status": "answered", "success": True}

    monkeypatch.setattr(run_bench, "run_task", flaky)
    row = run_bench.run_task_safely(TASKS[1], retries=1)
    assert attempts["n"] == 2
    assert row["status"] == "answered" and row["success"] is True
