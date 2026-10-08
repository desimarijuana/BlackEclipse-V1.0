"""Production-failure mining.

Turns a failed production run into a candidate regression task:

    Production Failure → Normalize → Classify → Deduplicate → Candidate

Duplicates are collapsed by a stable signature (labels + tool sequence + prompt),
so thousands of identical failures yield one candidate, not thousands of tests.
A candidate is NOT a test until a human/auto step validates its expected
behavior — this module never fabricates an expectation.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Optional

from .store import EvaluationStore
from .taxonomy import classify_failure
from .trajectory import Trajectory, capture_from_store


def _signature(prompt: str, labels: list[str], tool_sequence: list[str]) -> str:
    payload = "|".join([
        re.sub(r"\s+", " ", (prompt or "").strip().lower()),
        ",".join(sorted(labels)),
        ",".join(tool_sequence),
    ]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def _category_for(labels: list[str], tool_sequence: list[str]) -> str:
    mapping = {
        "safety": "safety",
        "hallucination": "adversarial",
        "calculation": "finance",
        "citation": "citations",
        "research": "research",
        "coding": "coding",
        "tool_execution": "tools",
        "tool_selection": "tools",
        "tool_arguments": "tools",
        "memory": "memory",
        "state": "core",
        "timeout": "recovery",
        "infrastructure": "recovery",
    }
    for label in labels:
        if label in mapping:
            return mapping[label]
    if any("browser" in name for name in tool_sequence):
        return "browser"
    return "regression"


def mine_failure(
    eval_store: EvaluationStore,
    *,
    run: dict[str, Any],
    events: list[dict[str, Any]],
    prompt: Optional[str] = None,
    source: str = "production",
) -> dict[str, Any]:
    """Normalize, classify and deduplicate ONE failed production run."""
    run_id = str(run.get("id") or run.get("runId") or "")
    trajectory = Trajectory.from_events(
        events, run_id=run_id, task_id=f"production.{run_id}", trial_id=run_id,
        final_answer={"output": run.get("output")},
        outcome={"status": run.get("status"), "error": run.get("error")},
    )
    labels = classify_failure([], trajectory, trajectory.outcome)
    prompt = prompt or str(run.get("query") or run.get("input") or "")
    tool_sequence = trajectory.tool_sequence()
    signature = _signature(prompt, labels, tool_sequence)

    if eval_store.candidate_exists(signature):
        return {"created": False, "deduplicated": True, "signature": signature, "labels": labels}

    category = _category_for(labels, tool_sequence)
    candidate_task = {
        "id": f"regression.{category}.{signature[:8]}",
        "version": 1,
        "category": "regression",
        "difficulty": "medium",
        "name": f"Mined failure {signature[:8]}",
        "description": f"Regression candidate from production run {run_id}",
        "input": {"prompt": prompt},
        "metadata": {
            "mined": True,
            "sourceRunId": run_id,
            "signature": signature,
            "originalLabels": labels,
            "originalToolSequence": tool_sequence,
            "expected_behavior": None,  # requires validation; never fabricated
        },
    }
    candidate_id = eval_store.save_candidate(
        signature=signature, source=source, category=category,
        labels=labels, status="candidate", task=candidate_task,
        detail={"runId": run_id, "toolSequence": tool_sequence},
    )
    return {
        "created": True, "deduplicated": False, "candidateId": candidate_id,
        "signature": signature, "labels": labels, "category": category,
        "task": candidate_task,
    }


def ingest_failures(eval_store: EvaluationStore, failures: list[dict[str, Any]]) -> dict[str, Any]:
    """Mine a batch of failed runs. Each entry: ``{"run": {...}, "events": [...]}``."""
    created, deduplicated = [], []
    for entry in failures:
        outcome = mine_failure(
            eval_store, run=entry.get("run") or {}, events=entry.get("events") or [],
            prompt=entry.get("prompt"),
        )
        (created if outcome.get("created") else deduplicated).append(outcome["signature"])
    return {"created": created, "deduplicated": deduplicated,
            "createdCount": len(created), "deduplicatedCount": len(deduplicated)}


def promote_candidate(
    eval_store: EvaluationStore,
    candidate_id: str,
    *,
    expected_behavior: dict[str, Any],
) -> dict[str, Any]:
    """Attach a validated expected behavior and mark a candidate promotable.

    The expected behavior is supplied by a human/auto validator; mining never
    invents the expected outcome of a failure.
    """
    candidates = [c for c in eval_store.list_candidates(limit=100000) if c["id"] == candidate_id]
    if not candidates:
        raise KeyError(f"unknown candidate {candidate_id}")
    task = candidates[0]["task"]
    task.setdefault("metadata", {})["expected_behavior"] = expected_behavior
    task["expected_output"] = expected_behavior.get("expected_output")
    task["expected_tools"] = expected_behavior.get("expected_tools", [])
    task["forbidden_tools"] = expected_behavior.get("forbidden_tools", [])
    task["graders"] = expected_behavior.get("graders", [{"name": "tool"}, {"name": "safety"}])
    eval_store.save_candidate(
        id=candidate_id, signature=candidates[0]["signature"], source=candidates[0]["source"],
        category=candidates[0]["category"], labels=candidates[0]["labels"],
        status="validated", task=task, detail=candidates[0]["detail"],
    )
    return {"candidateId": candidate_id, "status": "validated", "task": task}


def mine_from_store(eval_store: EvaluationStore, agent_store: Any, run_id: str) -> dict[str, Any]:
    """Mine one run directly from the runtime store."""
    run = agent_store.get_run(run_id) or {}
    events = agent_store.list_events(run_id) if hasattr(agent_store, "list_events") else []
    return mine_failure(eval_store, run=run, events=events)


def capture_trajectory(agent_store: Any, run_id: str, *, task_id: str = "production") -> Trajectory:
    return capture_from_store(agent_store, run_id, task_id=task_id, trial_id=run_id)


__all__ = [
    "capture_trajectory",
    "ingest_failures",
    "mine_failure",
    "mine_from_store",
    "promote_candidate",
]
