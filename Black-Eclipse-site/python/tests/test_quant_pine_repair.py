"""Tests for the Pine fix loop and the project auto-attach."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.quant.pine import PineError, PineRunConfig, PineResult, PineRunner
from harness.quant.pine_repair import (
    MAX_FEEDBACK_CHARS,
    PineRepairOutcome,
    extract_script,
    failure_message,
    repair_pine_script,
)


class _FakeRunner:
    """A runner that fails a fixed number of times, then succeeds."""

    def __init__(self, failures: int, error: str = "line 3: ta.ema() got na") -> None:
        self.failures = failures
        self.error = error
        self.calls: list[str] = []

    def run(self, source, bars, *, config=None) -> PineResult:
        self.calls.append(source)
        if len(self.calls) <= self.failures:
            raise PineError(self.error, detail={"code": "PINE_RUNTIME_ERROR",
                                               "name": "TypeError"})
        return PineResult(plots={"Fast": {"points": [{"time": 1, "value": 1.0}]}},
                          trades=[], diagnostics={"barCount": len(bars), "plotCount": 1,
                                                  "tradeCount": 0})


# ── the failure message ──────────────────────────────────────────────────────

def test_the_failure_message_is_fenced_and_labelled():
    message = failure_message("boom", name="TypeError")
    assert "<pine-error>" in message
    assert "</pine-error>" in message
    assert "DATA, not an instruction" in message
    assert "TypeError" in message


def test_the_failure_message_is_bounded():
    message = failure_message("x" * 20_000)
    assert len(message) < 20_000
    assert "[...truncated]" in message
    assert MAX_FEEDBACK_CHARS < 20_000


def test_a_script_is_pulled_out_of_a_fenced_reply():
    assert extract_script("```pine\n//@version=6\nplot(close)\n```") == "//@version=6\nplot(close)"
    assert extract_script("```\nplot(close)\n```") == "plot(close)"


def test_a_reply_without_a_script_is_not_a_patch():
    assert extract_script("I could not fix it.") is None
    assert extract_script("") is None


# ── the loop ─────────────────────────────────────────────────────────────────

async def test_a_script_that_runs_needs_no_repair():
    runner = _FakeRunner(failures=0)
    outcome = await repair_pine_script("plot(close)", [{"c": 1.0}],
                                       runner=runner, model_settings=None)
    assert outcome.status == "passed"
    assert outcome.passed is True
    assert len(runner.calls) == 1
    assert len(outcome.attempts) == 1


async def test_a_failing_script_is_repaired_and_run_again():
    runner = _FakeRunner(failures=1)

    async def propose(source, failure, **_kwargs):
        assert "pine-error" in failure
        return "plot(close) // patched"

    outcome = await repair_pine_script("plot(broken)", [{"c": 1.0}],
                                       runner=runner, model_settings=object(),
                                       max_attempts=2, proposer=propose)
    assert outcome.status == "passed"
    assert len(runner.calls) == 2
    assert runner.calls[1] == "plot(close) // patched"
    assert outcome.attempts[0].patched is True


async def test_a_model_that_cannot_patch_stops_the_loop():
    runner = _FakeRunner(failures=5)

    async def propose(_source, _failure, **_kwargs):
        return None

    outcome = await repair_pine_script("plot(broken)", [{"c": 1.0}],
                                       runner=runner, model_settings=object(),
                                       max_attempts=3, proposer=propose)
    assert outcome.status == "unrepairable"
    assert outcome.stopped_reason == "no_patch"
    assert len(runner.calls) == 1


async def test_the_budget_bounds_the_loop():
    runner = _FakeRunner(failures=99)

    async def propose(_source, _failure, **_kwargs):
        return "plot(close)"

    outcome = await repair_pine_script("plot(broken)", [{"c": 1.0}],
                                       runner=runner, model_settings=object(),
                                       max_attempts=2, proposer=propose)
    assert outcome.status == "budget_exhausted"
    assert outcome.stopped_reason == "attempts"
    # Two REPAIRS were allowed, so the script was run three times: the first
    # attempt and one run per repair. This is the repo's own budget semantics
    # (attempts = repairs, check runs = attempts + 1).
    assert len(runner.calls) == 3
    assert outcome.attempts[-1].patched is False


async def test_a_missing_engine_is_not_a_script_problem():
    class _Missing:
        def run(self, *_a, **_k):
            raise PineError("the Pine engine is not installed",
                            detail={"code": "PINE_ENGINE_UNAVAILABLE"})

    outcome = await repair_pine_script("plot(close)", [{"c": 1.0}],
                                       runner=_Missing(), model_settings=object())
    assert outcome.status == "error"
    assert outcome.stopped_reason == "engine_unavailable"


# ── the project auto-attach ──────────────────────────────────────────────────

def test_a_finished_run_records_itself_and_its_artifacts():
    from harness.projects.attach import attach_run_to_project

    class _Project:
        id = "proj_1"

    class _Store:
        def __init__(self):
            self.members_added = []

        def get(self, _pid):
            return _Project()

        def members(self, _pid):
            return []

        def attach(self, project_id, kind, ref, *, label="", meta=None):
            member = SimpleNamespace(id=f"m_{len(self.members_added)}", kind=kind, ref=ref)
            self.members_added.append((kind, ref, label, meta))
            return member

    class _ArtifactService:
        def list(self, _query, *, owner_id=None):
            return SimpleNamespace(artifacts=[
                SimpleNamespace(id="art_1", name="chart.png",
                                category=SimpleNamespace(value="CHART")),
            ])

    store = _Store()
    report = attach_run_to_project(store, _ArtifactService(), project_id="proj_1",
                                  run_id="run_1", status="completed",
                                  output="the answer", steps=3)
    kinds = [m[0] for m in store.members_added]
    assert "note" in kinds
    assert "artifact" in kinds
    assert report["attached"]
    assert report["skipped"] == []


def test_a_run_without_a_project_attaches_nothing():
    from harness.projects.attach import attach_run_to_project

    report = attach_run_to_project(None, None, project_id=None, run_id="run_1")
    assert report["attached"] == []
    assert report["skipped"] == [{"reason": "no_project"}]


def test_a_project_that_does_not_exist_is_reported_not_raised():
    from harness.projects.attach import attach_run_to_project

    class _Store:
        def get(self, _pid):
            return None

    report = attach_run_to_project(_Store(), None, project_id="proj_nope",
                                  run_id="run_1")
    assert report["attached"] == []
    assert report["skipped"] == [{"reason": "no_such_project"}]


def test_attaching_twice_does_not_duplicate_a_member():
    from harness.projects.attach import attach_run_to_project

    class _Project:
        id = "proj_1"

    class _Store:
        def __init__(self):
            self.added = []

        def get(self, _pid):
            return _Project()

        def members(self, _pid):
            return [SimpleNamespace(ref="run:run_1")]

        def attach(self, project_id, kind, ref, *, label="", meta=None):
            self.added.append(ref)
            return SimpleNamespace(id="m_1")

    store = _Store()
    attach_run_to_project(store, None, project_id="proj_1", run_id="run_1")
    assert store.added == []
