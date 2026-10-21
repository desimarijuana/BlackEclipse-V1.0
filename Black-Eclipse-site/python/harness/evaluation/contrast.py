"""Contrastive behavioral evidence — the Eclipse-native "Propose" substrate.

Proposals are never asked to reason about scores. The improver receives the
task, the FULL trajectories of a shared baseline and each candidate, each
candidate's behavioral diff against the baseline, and the proposer's own
decision notes -- then must cite the specific trajectory moment behind every
change: "one you cannot trace to a moment is speculation."

This module builds that bundle from Eclipse's own :class:`Trajectory` records.
It is deterministic and stdlib-only; it makes no model calls and reads no
evaluation verdicts -- :func:`render_evidence_bundle` enforces the last part
through :mod:`harness.evaluation.verdict_guard` before returning.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .trajectory import Trajectory
from .verdict_guard import assert_no_verdict_leaks

_METRIC_KEYS = (
    "events",
    "modelSteps",
    "toolCalls",
    "toolErrors",
    "retries",
    "promptTokens",
    "completionTokens",
    "totalTokens",
    "cost",
    "latencyMs",
)

_SUMMARY_KEYS = ("toolErrors", "retries", "modelSteps", "totalTokens", "cost", "latencyMs")

_CITATION_RULE = (
    "Cite the specific trajectory moment behind every change; one you cannot "
    "trace to a moment is speculation."
)


def _behavior_tokens(trajectory: Trajectory) -> list[str]:
    """One token per behavior step; tool identity survives, not just event type."""
    tokens: list[str] = []
    for event in trajectory.events:
        name = str(event.data.get("name") or "")
        if event.type == "tool.requested":
            tokens.append(f"call:{name or '?'}")
        elif event.type == "tool.completed":
            tokens.append(f"done:{name or '?'}")
        elif event.type == "tool.failed":
            tokens.append(f"fail:{name or '?'}")
        elif event.type == "tool.truncated":
            tokens.append(f"trunc:{name or '?'}")
        else:
            tokens.append(event.type)
    return tokens


def _first_divergence(baseline: list[str], candidate: list[str]) -> int | None:
    for index in range(min(len(baseline), len(candidate))):
        if baseline[index] != candidate[index]:
            return index
    if len(baseline) != len(candidate):
        return min(len(baseline), len(candidate))
    return None


def _metrics_delta(baseline: Trajectory, candidate: Trajectory) -> dict:
    delta: dict = {}
    base_metrics = baseline.metrics or {}
    cand_metrics = candidate.metrics or {}
    for key in _METRIC_KEYS:
        base_value = base_metrics.get(key)
        cand_value = cand_metrics.get(key)
        if base_value is None or cand_value is None:
            delta[key] = None
            continue
        try:
            delta[key] = round(float(cand_value) - float(base_value), 6)
        except (TypeError, ValueError):
            delta[key] = None
    return delta


def _outcome_of(trajectory: Trajectory) -> str:
    status = trajectory.outcome.get("status")
    return str(status) if status else "unknown"


@dataclass(frozen=True)
class ContrastReport:
    """Deterministic behavioral comparison of two real executions."""

    baseline_label: str
    candidate_label: str
    tool_sequence_baseline: tuple[str, ...]
    tool_sequence_candidate: tuple[str, ...]
    tool_sequence_diff: str
    outcome_baseline: str
    outcome_candidate: str
    metrics_delta: dict
    first_divergence_index: int | None
    summary: str

    def to_dict(self) -> dict:
        return {
            "baselineLabel": self.baseline_label,
            "candidateLabel": self.candidate_label,
            "toolSequenceBaseline": list(self.tool_sequence_baseline),
            "toolSequenceCandidate": list(self.tool_sequence_candidate),
            "toolSequenceDiff": self.tool_sequence_diff,
            "outcomeBaseline": self.outcome_baseline,
            "outcomeCandidate": self.outcome_candidate,
            "metricsDelta": dict(self.metrics_delta),
            "firstDivergenceIndex": self.first_divergence_index,
            "summary": self.summary,
        }


def contrast_trajectories(
    baseline: Trajectory,
    candidate: Trajectory,
    *,
    baseline_label: str = "baseline",
    candidate_label: str = "candidate",
) -> ContrastReport:
    """Contrast a candidate execution against a baseline execution, no model calls."""
    base_tokens = _behavior_tokens(baseline)
    cand_tokens = _behavior_tokens(candidate)
    divergence = _first_divergence(base_tokens, cand_tokens)

    base_seq = baseline.tool_sequence()
    cand_seq = candidate.tool_sequence()
    tool_diff = "".join(
        difflib.unified_diff(
            [f"{name}\n" for name in base_seq],
            [f"{name}\n" for name in cand_seq],
            fromfile=f"{baseline_label}/tools",
            tofile=f"{candidate_label}/tools",
        )
    )

    delta = _metrics_delta(baseline, candidate)
    base_outcome = _outcome_of(baseline)
    cand_outcome = _outcome_of(candidate)

    parts = [
        f"outcome {base_outcome}->{cand_outcome}",
        f"toolCalls {len(base_seq)}->{len(cand_seq)}",
    ]
    if divergence is not None:
        token = (
            cand_tokens[divergence]
            if divergence < len(cand_tokens)
            else base_tokens[divergence]
        )
        parts.append(f"first divergence at behavior step {divergence} ({token})")
    for key in _SUMMARY_KEYS:
        value = delta.get(key)
        if value:
            parts.append(f"{key} {value:+g}")

    return ContrastReport(
        baseline_label=baseline_label,
        candidate_label=candidate_label,
        tool_sequence_baseline=tuple(base_seq),
        tool_sequence_candidate=tuple(cand_seq),
        tool_sequence_diff=tool_diff,
        outcome_baseline=base_outcome,
        outcome_candidate=cand_outcome,
        metrics_delta=delta,
        first_divergence_index=divergence,
        summary="; ".join(parts) + ".",
    )


def _mission(mission_job: str, layout: list[str]) -> str:
    return (
        f"{mission_job.strip()}\n\n"
        "# YOUR EVIDENCE\n\n"
        "It is on disk, in this directory. Read it -- do not answer from this "
        "message alone.\n\n"
        + "\n".join(layout)
        + "\n\n"
        "Every trajectory event is present: trajectories are written in full and "
        "are not clipped to fit a mission. A tool result may carry an explicit "
        "truncation marker -- that marker is ours, not behavior by the solver; do "
        "not diagnose it as a failure.\n\n"
        "Read `task.md` and the baseline first, then inspect every candidate at "
        "least once before deciding. For each candidate, compare what changed in "
        "its behavior against the baseline, what improved, and what regressed or "
        "remained unresolved. " + _CITATION_RULE + "\n"
    )


def render_evidence_bundle(
    directory: Path | str,
    *,
    task_text: str,
    mission_job: str,
    trajectories: Mapping[str, Trajectory],
    baseline_label: str,
    produced: Mapping[str, str] | None = None,
    decisions: Mapping[str, str] | None = None,
) -> Path:
    """Write the contrastive evidence bundle; return its root directory.

    Files: ``task.md``; ``rollouts/<label>.md`` (full trajectories);
    ``diffs/<label>.md`` (behavior diff vs the baseline, metric deltas, decision
    notes); ``produced/<label>.md`` and ``decisions/<label>.md`` when supplied;
    ``MISSION.md`` (the pointer with the citation rule). Raises
    :class:`VerdictLeakError` when anything in the bundle carries evaluation
    verdicts or expected answers.
    """
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    produced = dict(produced or {})
    decisions = dict(decisions or {})

    if baseline_label not in trajectories:
        raise ValueError(
            f"baseline label {baseline_label!r} is not among {sorted(trajectories)}"
        )

    (root / "task.md").write_text(task_text, encoding="utf-8")

    labels = sorted(trajectories)
    others = [label for label in labels if label != baseline_label]
    layout = [
        "task.md                     the task as the agent received it",
        "rollouts/<label>.md         FULL trajectories: " + ", ".join(labels),
    ]
    if others:
        layout.append(
            "diffs/<label>.md            behavior vs " + baseline_label + ": " + ", ".join(others)
        )
    if produced:
        layout.append(
            "produced/<label>.md         what each candidate produced: " + ", ".join(sorted(produced))
        )
    if decisions:
        layout.append(
            "decisions/<label>.md        the proposer's own notes: " + ", ".join(sorted(decisions))
        )

    rollouts_dir = root / "rollouts"
    rollouts_dir.mkdir(exist_ok=True)
    for label in labels:
        trajectory = trajectories[label]
        body = (
            f"<!-- full trajectory, {len(trajectory.events)} events, not truncated -->\n\n"
            + json.dumps(trajectory.to_dict(), indent=2, sort_keys=True)
        )
        (rollouts_dir / f"{label}.md").write_text(body, encoding="utf-8")

    if others:
        diffs_dir = root / "diffs"
        diffs_dir.mkdir(exist_ok=True)
        baseline = trajectories[baseline_label]
        for label in others:
            report = contrast_trajectories(
                baseline,
                trajectories[label],
                baseline_label=baseline_label,
                candidate_label=label,
            )
            section = [
                f"# {label} vs {baseline_label}",
                "",
                f"_{report.summary}_",
                "",
                "```diff",
                report.tool_sequence_diff.rstrip("\n") or "(no tool sequence difference)",
                "```",
                "",
                "## Metric deltas (candidate minus baseline)",
                "",
            ]
            for key, value in report.metrics_delta.items():
                if value is None:
                    section.append(f"- {key}: not measured on one side")
                elif value:
                    section.append(f"- {key}: {value:+g}")
            section += [
                "",
                "## Decision notes",
                "",
                decisions.get(label, "No decision notes were recorded."),
            ]
            (diffs_dir / f"{label}.md").write_text("\n".join(section) + "\n", encoding="utf-8")

    if produced:
        produced_dir = root / "produced"
        produced_dir.mkdir(exist_ok=True)
        for label in sorted(produced):
            (produced_dir / f"{label}.md").write_text(str(produced[label]), encoding="utf-8")

    if decisions:
        decisions_dir = root / "decisions"
        decisions_dir.mkdir(exist_ok=True)
        for label in sorted(decisions):
            (decisions_dir / f"{label}.md").write_text(str(decisions[label]), encoding="utf-8")

    (root / "MISSION.md").write_text(_mission(mission_job, layout), encoding="utf-8")

    assert_no_verdict_leaks(root)
    return root


__all__ = [
    "ContrastReport",
    "contrast_trajectories",
    "render_evidence_bundle",
]
