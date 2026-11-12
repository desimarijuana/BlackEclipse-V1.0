"""Release gate for the C7 SLO report (pure logic + CLI-friendly helpers).

The gate is intentionally dumb and auditable: it reads a JSON report produced by
`harness.observability.probe` (or by `GET /observability/release-report` in a
real deployment), compares it with budgets and an optional committed baseline,
and returns one check per objective. No network, no model, no hidden state.

Exit codes (in `probe_slo.py`): 0 healthy, 1 breach/regression, 2 malformed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

REPORT_SCHEMA = 1


class GateError(ValueError):
    """The report or budgets file is malformed."""


@dataclass
class GateCheck:
    name: str
    ok: bool
    actual: Any = None
    budget: Any = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "ok": self.ok, "actual": self.actual,
            "budget": self.budget, "reason": self.reason,
        }


@dataclass
class GateResult:
    ok: bool
    checks: list[GateCheck] = field(default_factory=list)
    reportGeneratedAt: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "reportGeneratedAt": self.reportGeneratedAt,
            "checks": [check.to_dict() for check in self.checks],
            "failures": [check.to_dict() for check in self.checks if not check.ok],
        }


def load_json(path: str | Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise GateError(f"file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GateError(f"{path} must contain a JSON object")
    return data


def validate_report(report: dict[str, Any]) -> None:
    if not isinstance(report, dict):
        raise GateError("report must be an object")
    if not isinstance(report.get("runs"), dict):
        raise GateError("report.runs is required")
    created = report["runs"].get("created")
    terminal = report["runs"].get("terminal")
    if not isinstance(created, int) or not isinstance(terminal, int):
        raise GateError("report.runs.created/terminal must be integers")
    for section in ("latency", "resume", "cost"):
        if not isinstance(report.get(section), dict):
            raise GateError(f"report.{section} is required")


def _value(section: dict[str, Any], key: str) -> Optional[float]:
    value = section.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _regression(
    name: str, actual: Optional[float], baseline: Optional[float], max_regression: Optional[float],
) -> Optional[GateCheck]:
    if actual is None or baseline is None or baseline <= 0 or max_regression is None:
        return None
    allowed = baseline * (1.0 + float(max_regression))
    return GateCheck(
        name=f"{name}_regression",
        ok=actual <= allowed,
        actual=round(actual, 4),
        budget=round(allowed, 4),
        reason=(
            "within the committed regression allowance"
            if actual <= allowed else
            f"regressed {(actual / baseline - 1.0) * 100:.1f}% vs baseline "
            f"(max {float(max_regression) * 100:.1f}%)"
        ),
    )


def evaluate_gate(
    report: dict[str, Any],
    budgets: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
) -> GateResult:
    """Evaluate every budget. A missing sample skips that check honestly."""
    validate_report(report)
    configured = budgets.get("budgets")
    if not isinstance(configured, dict) or not configured:
        raise GateError("budgets.budgets must be a non-empty object")
    baseline = baseline or {}
    checks: list[GateCheck] = []

    runs = report["runs"]
    created = int(runs.get("created") or 0)
    terminal = int(runs.get("terminal") or 0)
    orphaned = int(runs.get("orphaned") or 0)

    terminal_budget = configured.get("terminal_correctness") or {}
    if created > 0:
        target = float(terminal_budget.get("target", 0.999))
        ratio = min(1.0, terminal / created)
        checks.append(GateCheck(
            "terminal_correctness", ratio >= target, round(ratio, 5), target,
            "every run reached a terminal state" if ratio >= target
            else f"{created - terminal} run(s) never reached a terminal state",
        ))
    else:
        checks.append(GateCheck("terminal_correctness", False, 0, terminal_budget.get("target"),
                                "no runs were recorded"))

    orphan_budget = configured.get("orphan_rate") or {}
    if created > 0:
        allowed_orphans = float(orphan_budget.get("max", 0.0))
        rate = orphaned / created
        checks.append(GateCheck(
            "orphan_rate", rate <= allowed_orphans, round(rate, 5), allowed_orphans,
            "no orphaned runs" if rate <= allowed_orphans
            else f"{orphaned} orphaned run(s) of {created}",
        ))

    latency = report["latency"]
    latency_budget = configured.get("run_p95_latency") or {}
    if latency.get("samples"):
        p95 = _value(latency, "p95")
        threshold = latency_budget.get("thresholdMs")
        if p95 is not None and threshold is not None:
            target = float(threshold)
            checks.append(GateCheck(
                "run_p95_latency", p95 <= target, round(p95, 3), target,
                "p95 within budget" if p95 <= target else f"p95 {p95:.0f}ms > {target:.0f}ms",
            ))
            regression = _regression(
                "run_p95_latency", p95, _value(baseline.get("latency") or {}, "p95"),
                latency_budget.get("maxRegression"),
            )
            if regression is not None:
                checks.append(regression)

    resume = report["resume"]
    resume_budget = configured.get("resume_p95") or {}
    if resume.get("samples"):
        p95 = _value(resume, "p95")
        threshold = resume_budget.get("thresholdMs")
        if p95 is not None and threshold is not None:
            target = float(threshold)
            checks.append(GateCheck(
                "resume_p95", p95 <= target, round(p95, 3), target,
                "resume p95 within budget" if p95 <= target else f"resume p95 {p95:.0f}ms > {target:.0f}ms",
            ))
            regression = _regression(
                "resume_p95", p95, _value(baseline.get("resume") or {}, "p95"),
                resume_budget.get("maxRegression"),
            )
            if regression is not None:
                checks.append(regression)

    cost = report["cost"]
    cost_budget = configured.get("cost_per_task") or {}
    if cost.get("samples"):
        p95 = _value(cost, "perTaskP95")
        threshold = cost_budget.get("thresholdUsd")
        if p95 is not None and threshold is not None:
            target = float(threshold)
            checks.append(GateCheck(
                "cost_per_task", p95 <= target, round(p95, 6), target,
                "cost per task within budget" if p95 <= target
                else f"cost p95 ${p95:.4f} > ${target:.4f}",
            ))
            regression = _regression(
                "cost_per_task", p95, _value(baseline.get("cost") or {}, "perTaskP95"),
                cost_budget.get("maxRegression"),
            )
            if regression is not None:
                checks.append(regression)

    return GateResult(
        ok=all(check.ok for check in checks), checks=checks,
        reportGeneratedAt=report.get("generatedAt"),
    )


__all__ = [
    "GateCheck",
    "GateError",
    "GateResult",
    "REPORT_SCHEMA",
    "evaluate_gate",
    "load_json",
    "validate_report",
]
