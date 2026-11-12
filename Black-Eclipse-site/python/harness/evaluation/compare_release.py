"""Compare two release evaluation reports (C8.6).

Two releases publish comparable numbers only when they measured the same
datasets, versions, checksums, tier and grader version. This module refuses to
compare apples to oranges: an incomparable pair is reported with the exact
reason, never silently blended.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1


class CompareError(ValueError):
    pass


def validate(report: dict[str, Any]) -> None:
    if not isinstance(report, dict):
        raise CompareError("report must be an object")
    if not isinstance(report.get("datasets"), dict):
        raise CompareError("report.datasets is required")
    if not isinstance(report.get("metrics"), dict):
        raise CompareError("report.metrics is required")


def _identity(dataset: dict[str, Any]) -> tuple[Any, ...]:
    return (
        dataset.get("version"), dataset.get("checksum"),
        dataset.get("tier"), dataset.get("graderVersion"),
    )


def compare(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    validate(current)
    validate(previous)
    reasons: list[str] = []
    current_sets = current["datasets"]
    previous_sets = previous["datasets"]

    if set(current_sets) != set(previous_sets):
        reasons.append(
            "dataset set differs: "
            f"current={sorted(current_sets)} previous={sorted(previous_sets)}"
        )
    for name in sorted(set(current_sets) & set(previous_sets)):
        if _identity(current_sets[name]) != _identity(previous_sets[name]):
            reasons.append(f"{name}: version/checksum/tier/grader changed")

    deltas: dict[str, Any] = {}
    for key, value in current["metrics"].items():
        if key not in previous["metrics"]:
            continue
        before = previous["metrics"][key]
        if isinstance(value, (int, float)) and isinstance(before, (int, float)):
            deltas[key] = {
                "previous": before,
                "current": value,
                "delta": round(float(value) - float(before), 6),
            }
        elif value != before:
            deltas[key] = {"previous": before, "current": value, "delta": None}

    return {
        "comparable": not reasons,
        "reasons": reasons,
        "deltas": deltas,
        "current": current.get("release") or current.get("generatedAt"),
        "previous": previous.get("release") or previous.get("generatedAt"),
    }


def load(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CompareError(f"cannot read {path}: {exc}") from exc
    return data


__all__ = ["SCHEMA_VERSION", "CompareError", "compare", "load", "validate"]


if __name__ == "__main__":  # pragma: no cover - CLI entry
    from .compare_release_main import main

    raise SystemExit(main())
