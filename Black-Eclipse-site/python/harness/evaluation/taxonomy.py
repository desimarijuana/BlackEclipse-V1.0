"""Failure taxonomy: every failed evaluation is classifiable.

A failure may carry more than one label (a wrong tool with wrong arguments is
both ``tool_selection`` and ``tool_arguments``). The classifier is deterministic
and derived from structured signals — grader results, trajectory events and the
trial outcome — never from model prose.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable

# Grader name → the failure labels it can justify when it fails.
_GRADER_LABELS: dict[str, tuple[str, ...]] = {
    "exact": ("reasoning",),
    "semantic": ("reasoning",),
    "state": ("state",),
    "tool": ("tool_selection", "tool_arguments", "tool_execution"),
    "research": ("research", "evidence"),
    "citation": ("citation",),
    "financial": ("calculation",),
    "code": ("coding",),
    "browser": ("browser",),
    "memory": ("memory",),
    "safety": ("safety",),
    "hallucination": ("hallucination",),
}


class FailureLabel(str, Enum):
    PLANNING = "planning"
    REASONING = "reasoning"
    MODEL = "model"
    TOOL_SELECTION = "tool_selection"
    TOOL_ARGUMENTS = "tool_arguments"
    TOOL_EXECUTION = "tool_execution"
    TOOL_RESULT_INTERPRETATION = "tool_result_interpretation"
    CONTEXT = "context"
    MEMORY = "memory"
    RETRIEVAL = "retrieval"
    RESEARCH = "research"
    EVIDENCE = "evidence"
    CITATION = "citation"
    CALCULATION = "calculation"
    CODING = "coding"
    BROWSER = "browser"
    STATE = "state"
    TIMEOUT = "timeout"
    HALLUCINATION = "hallucination"
    SAFETY = "safety"
    INFRASTRUCTURE = "infrastructure"


def classify_failure(
    grader_results: Iterable[Any],
    trajectory: Any = None,
    outcome: dict[str, Any] | None = None,
) -> list[str]:
    """Return the (deduplicated, ordered) set of failure labels for a trial.

    ``grader_results`` are :class:`~harness.evaluation.graders.GraderResult` (or
    any object with ``grader``/``passed``/``failures``); ``trajectory`` is a
    :class:`~harness.evaluation.trajectory.Trajectory`.
    """
    labels: list[str] = []

    def add(label: str) -> None:
        if label not in labels:
            labels.append(label)

    outcome = outcome or {}
    for result in grader_results:
        if getattr(result, "passed", True):
            continue
        name = getattr(result, "grader", "") or ""
        for label in _GRADER_LABELS.get(name, ()):
            add(label)
        # grader-specific refinement
        failures = " ".join(str(f) for f in (getattr(result, "failures", None) or []))
        if name == "tool":
            if "sequence" in failures or "order" in failures:
                add(FailureLabel.PLANNING.value)
            if "interpre" in failures or "result" in failures:
                add(FailureLabel.TOOL_RESULT_INTERPRETATION.value)
        if name == "financial" and ("formula" in failures or "value" in failures):
            add(FailureLabel.CALCULATION.value)

    status = str(outcome.get("status") or "")
    error = outcome.get("error")
    if status == "timeout":
        add(FailureLabel.TIMEOUT.value)
    if status == "failed" and not labels:
        add(FailureLabel.INFRASTRUCTURE.value)

    if trajectory is not None:
        for call in getattr(trajectory, "tool_calls", lambda: [])():
            if call.get("status") == "failed" and not call.get("error", {}).get("code") == "POLICY_DENIED":
                add(FailureLabel.TOOL_EXECUTION.value)
        for event in getattr(trajectory, "events", []):
            if event.type == "context.overflow":
                add(FailureLabel.CONTEXT.value)
            if event.type in ("run.failed",) and isinstance(event.data, dict):
                code = str(event.data.get("code") or "")
                if "MODEL" in code or "PROVIDER" in code:
                    add(FailureLabel.MODEL.value)

    if not labels and error:
        add(FailureLabel.INFRASTRUCTURE.value)
    return labels


__all__ = ["FailureLabel", "classify_failure"]
