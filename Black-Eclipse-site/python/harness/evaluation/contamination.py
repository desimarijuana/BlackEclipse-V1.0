"""Contamination control: who may read which split, and what a canary proves.

The corpus has four splits and they are NOT interchangeable:

- `optimization` — the search may propose and measure against it;
- `validation`   — the acceptance set; the search may not train on it;
- `held_out`     — the canary; only a post-validation check may read it;
- `release`      — the release gate's private set.

A decoy canary is a task whose expected answer is deliberately wrong. A
candidate that "passes" it may be optimising the answer rather than the
behaviour, so the pass is a hard failure (`CANARY_HACK`), not a success.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Sequence

from .tasks import SPLITS, task_split

PURPOSES: tuple[str, ...] = ("optimization", "validation", "canary", "release")

# Which split each purpose may read. A purpose reads exactly its own split.
PURPOSE_SPLITS: dict[str, frozenset[str]] = {
    "optimization": frozenset({"optimization"}),
    "validation": frozenset({"validation"}),
    "canary": frozenset({"held_out"}),
    "release": frozenset({"release"}),
}


class ContaminationError(ValueError):
    """A split/access rule was violated; `code` is stable and testable."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


def _meta(task: Any) -> Mapping[str, Any]:
    return getattr(task, "metadata", None) or {}


def has_oracle(task: Any) -> bool:
    """True when the task names an independent oracle for its expected value."""
    return bool(_meta(task).get("oracle") or _meta(task).get("recomputed"))


def is_oracle_exempt(
    task: Any, dataset_metadata: Optional[Mapping[str, Any]] = None,
) -> bool:
    """A task (or its whole dataset) deliberately predates the oracle rule.

    Exemption is not a substitute for an oracle: it records that the task's
    expected behaviour cannot be independently recomputed (a refusal, a route,
    a frozen team comparison), so the strict audit must not call it a gap.
    """
    return bool(
        _meta(task).get("oracleExempt")
        or (dataset_metadata or {}).get("oracleExempt")
    )


def oracle_reason(
    task: Any, dataset_metadata: Optional[Mapping[str, Any]] = None,
) -> str:
    """Why an exempt task has no recomputation oracle (empty if none declared)."""
    return str(
        _meta(task).get("oracleReason")
        or (dataset_metadata or {}).get("oracleReason")
        or ""
    )


def has_contamination(
    task: Any, dataset_metadata: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Task-level provenance, or the dataset-level provenance that covers it."""
    return bool(
        _meta(task).get("contamination")
        or (dataset_metadata or {}).get("contamination")
    )


def is_canary(task: Any) -> bool:
    """A decoy task: passing it is evidence of answer-fitting, not capability."""
    return bool(_meta(task).get("canary") or _meta(task).get("decoy"))


def _split(
    task: Any,
    dataset_split: str = "",
    split_by_id: Optional[dict[str, str]] = None,
) -> str:
    return task_split(task, dataset_split, split_by_id)


def access_guard(
    task: Any,
    purpose: str,
    *,
    dataset_split: str = "",
    split_by_id: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Assert that `purpose` may read this task's split; raise otherwise."""
    wanted = str(purpose or "").strip().lower()
    if wanted not in PURPOSE_SPLITS:
        raise ContaminationError(
            "UNKNOWN_PURPOSE",
            f"unknown corpus purpose {purpose!r} (expected {', '.join(PURPOSES)})",
        )
    split = _split(task, dataset_split, split_by_id)
    if split not in SPLITS:
        raise ContaminationError(
            "UNKNOWN_SPLIT", f"task {getattr(task, 'id', '?')} has split {split!r}",
        )
    if split not in PURPOSE_SPLITS[wanted]:
        raise ContaminationError(
            "CONTAMINATION_SPLIT",
            f"task {getattr(task, 'id', '?')} is {split!r}; "
            f"{wanted!r} may read {sorted(PURPOSE_SPLITS[wanted])}",
        )
    if wanted == "validation" and is_canary(task):
        raise ContaminationError(
            "CANARY_IN_VALIDATION",
            f"task {getattr(task, 'id', '?')} is a decoy canary and cannot be "
            "an acceptance task",
        )
    return {
        "taskId": getattr(task, "id", None),
        "split": split,
        "purpose": wanted,
        "canary": is_canary(task),
        "oracle": has_oracle(task),
    }


def select_for_purpose(
    tasks: Iterable[Any],
    purpose: str,
    *,
    dataset_split: str = "",
    split_by_id: Optional[dict[str, str]] = None,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """Split a task list into allowed and refused-with-reason for one purpose."""
    allowed: list[Any] = []
    refused: list[dict[str, Any]] = []
    for task in tasks or ():
        try:
            access_guard(
                task, purpose,
                dataset_split=dataset_split, split_by_id=split_by_id,
            )
        except ContaminationError as exc:
            refused.append({
                "taskId": getattr(task, "id", None),
                "split": _split(task, dataset_split, split_by_id),
                "code": exc.code,
                "detail": exc.detail,
            })
            continue
        allowed.append(task)
    return allowed, refused


def assert_no_canary_hack(task: Any, passed: bool) -> None:
    """A decoy canary that PASSES is a hard failure, not a success."""
    if is_canary(task) and passed:
        raise ContaminationError(
            "CANARY_HACK",
            f"decoy canary {getattr(task, 'id', '?')} passed: the candidate is "
            "fitting the expected answer instead of the behaviour",
        )


def contamination_summary(tasks: Sequence[Any]) -> dict[str, Any]:
    """A bounded, honest view of the corpus splits and their metadata."""
    by_split: dict[str, int] = {}
    canaries = 0
    with_oracle = 0
    with_metadata = 0
    for task in tasks or ():
        split = _split(task)
        by_split[split] = by_split.get(split, 0) + 1
        if is_canary(task):
            canaries += 1
        if has_oracle(task):
            with_oracle += 1
        if _meta(task).get("contamination"):
            with_metadata += 1
    total = sum(by_split.values())
    return {
        "tasks": total,
        "bySplit": dict(sorted(by_split.items())),
        "canaries": canaries,
        "withOracle": with_oracle,
        "oracleCoverage": round(with_oracle / total, 6) if total else 0.0,
        "withContaminationMetadata": with_metadata,
    }


__all__ = [
    "ContaminationError",
    "PURPOSES",
    "PURPOSE_SPLITS",
    "access_guard",
    "assert_no_canary_hack",
    "contamination_summary",
    "has_contamination",
    "has_oracle",
    "is_canary",
    "is_oracle_exempt",
    "oracle_reason",
    "select_for_purpose",
]
