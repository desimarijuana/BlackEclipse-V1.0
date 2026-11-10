"""Pinned live-tier baselines, comparison and the published report."""

from __future__ import annotations

import pytest

from harness.evaluation.live_baseline import (
    build_live_baseline,
    compare_live_baseline,
    find_live_baseline,
    live_key,
    publish_report,
    read_live_baselines,
    write_live_baseline,
)


class _Score:
    cost = 0.01
    latency_ms = 10.0


class _Trial:
    def __init__(self, passed: bool):
        self.passed = passed
        self.unmeasured = False
        self.score = _Score()


class _Task:
    def __init__(self, task_id: str):
        self.id = task_id
        self.category = "core"


class _TaskResult:
    def __init__(self, task_id: str, passed: bool):
        self.task = _Task(task_id)
        self.trials = [_Trial(passed)]


class _Suite:
    def __init__(self, passes):
        self.run_id = "run-live"
        self.dataset_name = "benchmark_v1"
        self.dataset_version = "1.0.0"
        self.dataset_checksum = "checksum-1"
        self.tasks = [
            _TaskResult(f"t{index}", passed)
            for index, passed in enumerate(passes)
        ]
        total = len(passes)
        successes = sum(1 for passed in passes if passed)
        self.aggregates = {
            "task_success": successes / total if total else None,
            "safety_score": 1.0,
        }
        self.categories = {
            "core": {"passed": successes, "measured": total, "passRate": successes / total}
        }
        self.tier = 2
        self.agent_version = "1.0.0"
        self.git_commit = "deadbeef"


def _entry(suite=None, *, prompt="prompt-a"):
    suite = suite or _Suite([True] * 6)
    return build_live_baseline(
        suite,
        provider="openai",
        model="gpt-test",
        tier="live",
        prompt_hash=prompt,
        recorded_at="2026-10-22T00:00:00.000Z",
    )


def test_a_live_baseline_requires_the_live_tier_and_an_identity():
    suite = _Suite([True] * 4)
    with pytest.raises(ValueError):
        build_live_baseline(
            suite, provider="p", model="m", tier="scripted",
        )
    with pytest.raises(ValueError):
        build_live_baseline(suite, provider="", model="m", tier="live")
    with pytest.raises(ValueError):
        build_live_baseline(suite, provider="p", model="", tier="live")


def test_a_live_baseline_carries_identity_measures_and_no_secret():
    entry = _entry()
    assert entry["tier"] == "live"
    assert entry["provider"] == "openai"
    assert entry["model"] == "gpt-test"
    assert entry["taskSuccess"] == 1.0
    assert entry["taskCount"] == 6
    assert entry["ci"][0] is not None and entry["ci"][1] > 0.99
    assert entry["key"] == live_key(
        provider="openai", model="gpt-test", prompt_hash="prompt-a",
        dataset_checksum="checksum-1",
    )
    dumped = repr(entry).lower()
    assert "api_key" not in dumped and "apikey" not in dumped


def test_registry_roundtrip_and_key_includes_prompt(tmp_path):
    path = tmp_path / "live_v1.json"
    entry = _entry()
    write_live_baseline(entry, path=str(path))
    registry = read_live_baselines(str(path))
    found = find_live_baseline(
        registry,
        provider="openai",
        model="gpt-test",
        prompt_hash="prompt-a",
        dataset_checksum="checksum-1",
    )
    assert found is not None and found["key"] == entry["key"]

    other_prompt = find_live_baseline(
        registry,
        provider="openai",
        model="gpt-test",
        prompt_hash="prompt-b",
        dataset_checksum="checksum-1",
    )
    assert other_prompt is None


def test_a_matching_suite_compares_clean():
    baseline = _entry()
    comparison = compare_live_baseline(baseline, _Suite([True] * 6))
    assert comparison["ok"] is True
    assert comparison["delta"] == 0.0
    assert comparison["regressions"] == []
    assert comparison["pairedTasks"] == 6


def test_a_critical_regression_fails_the_comparison():
    baseline = _entry()
    comparison = compare_live_baseline(
        baseline, _Suite([True, True, True, False, False, False]),
    )
    assert comparison["ok"] is False
    assert any(
        row.get("dimension") == "task_success"
        for row in comparison["regressions"]
    )
    assert comparison["delta"] < 0


def test_the_report_names_the_tier_identity_and_verdict(tmp_path):
    entry = _entry()
    target = tmp_path / "report.md"
    path = publish_report(entry, comparison=None, path=str(target))
    text = target.read_text(encoding="utf-8")
    assert path == str(target)
    assert "tier: **live**" in text
    assert "`openai` / `gpt-test`" in text
    assert "**NOT COMPARED**" in text
    assert "This report is live-model evidence only" in text


def test_the_report_marks_a_failed_comparison(tmp_path):
    baseline = _entry()
    comparison = compare_live_baseline(
        baseline, _Suite([True, True, False, False, False, False]),
    )
    target = tmp_path / "report.md"
    publish_report(baseline, comparison=comparison, path=str(target))
    text = target.read_text(encoding="utf-8")
    assert "**FAIL**" in text
    assert "task_success" in text


def test_live_baseline_flags_require_the_live_tier():
    from harness.evaluation import nightly

    assert nightly.main(["--publish"]) == 2
    assert nightly.main(["--write-live-baseline"]) == 2
    assert nightly.main(["--live-baseline"]) == 2


def test_the_published_report_uses_the_pinned_baseline_when_no_run_is_recorded():
    from harness.evaluation.report import _latest_live_baseline, to_benchmarks

    live, reason = _latest_live_baseline()
    assert reason == ""
    assert live is not None
    # The newest pinned live baseline (`live:27c280164943e63520e14422a6c953cf`)
    # measured task_success 0.9748. The older 0.9574 and 0.8520 pins (ADR-071)
    # are superseded by the newest passing run in `baselines/live_v1.json`.
    assert live.aggregates["task_success"] == pytest.approx(0.9748, abs=0.001)
    text = to_benchmarks(None, live)
    live_section = text.split("## Live tier", 1)[1]
    assert "NOT MEASURED" not in live_section
    assert "task_success" in live_section
