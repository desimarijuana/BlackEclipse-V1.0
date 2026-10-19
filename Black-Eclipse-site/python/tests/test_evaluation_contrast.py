"""Behavioral contrast + the contrastive evidence bundle (Harness² borrowings)."""

from __future__ import annotations

import json

import pytest

from harness.evaluation.contrast import contrast_trajectories, render_evidence_bundle
from harness.evaluation.trajectory import Trajectory
from harness.evaluation.verdict_guard import VerdictLeakError


def _events(sequence):
    return [
        {"type": event_type, "at": f"t{index}", "data": data}
        for index, (event_type, data) in enumerate(sequence)
    ]


def _baseline():
    return Trajectory.from_events(
        _events(
            [
                ("run.started", {}),
                ("tool.requested", {"name": "read_file", "toolCallId": "c1"}),
                ("tool.completed", {"toolCallId": "c1", "durationMs": 5}),
                ("tool.requested", {"name": "legacy_lookup", "toolCallId": "c2"}),
                ("tool.failed", {"toolCallId": "c2", "code": "TOOL_ERROR"}),
                ("run.completed", {}),
            ]
        ),
        run_id="run-base",
        task_id="task.x",
        trial_id="t-base",
        outcome={"status": "completed"},
    )


def _candidate():
    return Trajectory.from_events(
        _events(
            [
                ("run.started", {}),
                ("tool.requested", {"name": "read_file", "toolCallId": "c1"}),
                ("tool.completed", {"toolCallId": "c1", "durationMs": 4}),
                ("tool.requested", {"name": "modern_lookup", "toolCallId": "c2"}),
                ("tool.completed", {"toolCallId": "c2", "durationMs": 7}),
                ("run.completed", {}),
            ]
        ),
        run_id="run-cand",
        task_id="task.x",
        trial_id="t-cand",
        outcome={"status": "completed"},
    )


def test_contrast_reports_behavior_difference():
    report = contrast_trajectories(_baseline(), _candidate())
    assert report.first_divergence_index == 3
    assert report.tool_sequence_baseline == ("read_file", "legacy_lookup")
    assert report.tool_sequence_candidate == ("read_file", "modern_lookup")
    assert "legacy_lookup" in report.tool_sequence_diff
    assert "modern_lookup" in report.tool_sequence_diff
    assert report.metrics_delta["toolErrors"] == -1
    assert "first divergence at behavior step 3" in report.summary
    assert "toolErrors -1" in report.summary
    assert report.outcome_baseline == "completed"


def test_identical_trajectories_have_no_divergence():
    report = contrast_trajectories(_baseline(), _baseline(), candidate_label="copy")
    assert report.first_divergence_index is None
    assert report.tool_sequence_diff == ""
    assert all(value in (0.0, 0, None) for value in report.metrics_delta.values())
    assert "first divergence" not in report.summary


def test_prefix_diverges_at_min_length():
    baseline = Trajectory.from_events(
        _events([("run.started", {}), ("run.completed", {})]),
        run_id="a",
        task_id="t",
        trial_id="a",
    )
    candidate = Trajectory.from_events(
        _events([("run.started", {}), ("model.requested", {}), ("run.completed", {})]),
        run_id="b",
        task_id="t",
        trial_id="b",
    )
    report = contrast_trajectories(baseline, candidate)
    assert report.first_divergence_index == 1


def test_render_bundle_writes_the_layout(tmp_path):
    root = render_evidence_bundle(
        tmp_path / "bundle",
        task_text="Fix the failing integration.",
        mission_job="Propose one minimal harness edit.",
        trajectories={"base": _baseline(), "cand": _candidate()},
        baseline_label="base",
        produced={"cand": "patched report"},
        decisions={"cand": "swapped to the modern lookup"},
    )
    assert (root / "MISSION.md").is_file()
    assert (root / "task.md").is_file()
    assert (root / "rollouts" / "base.md").is_file()
    assert (root / "rollouts" / "cand.md").is_file()
    assert (root / "diffs" / "cand.md").is_file()
    assert (root / "produced" / "cand.md").is_file()
    assert (root / "decisions" / "cand.md").is_file()

    mission = (root / "MISSION.md").read_text(encoding="utf-8")
    assert "Cite the specific trajectory moment" in mission
    assert "do not answer from this message alone" in mission
    assert "Fix the failing integration." in (root / "task.md").read_text(encoding="utf-8")

    distinct = (root / "diffs" / "cand.md").read_text(encoding="utf-8")
    assert "toolErrors" in distinct and "modern_lookup" in distinct
    assert "swapped to the modern lookup" in distinct

    raw = json.loads((root / "rollouts" / "cand.md").read_text(encoding="utf-8").split("\n\n", 1)[1])
    assert raw["runId"] == "run-cand"


def test_render_bundle_refuses_verdict_leaks(tmp_path):
    with pytest.raises(VerdictLeakError, match="weighted_composite"):
        render_evidence_bundle(
            tmp_path / "bundle",
            task_text="Fix the failing integration.",
            mission_job="Propose one minimal edit.",
            trajectories={"base": _baseline(), "cand": _candidate()},
            baseline_label="base",
            produced={"cand": "the run reached weighted_composite 0.91"},
        )


def test_render_bundle_requires_the_baseline(tmp_path):
    with pytest.raises(ValueError, match="baseline label"):
        render_evidence_bundle(
            tmp_path / "bundle",
            task_text="t",
            mission_job="j",
            trajectories={"base": _baseline()},
            baseline_label="nope",
        )
