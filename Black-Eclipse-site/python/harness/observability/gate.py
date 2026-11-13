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
    # W8: pass | fail | skipped | unmeasured | observed. `ok` stays the single
    # failure signal; `status` explains a non-failure that was not measured.
    status: str = ""
    samples: Optional[int] = None
    enforced: bool = True

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "pass" if self.ok else "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "ok": self.ok, "status": self.status,
            "actual": self.actual, "budget": self.budget,
            "samples": self.samples, "enforced": self.enforced, "reason": self.reason,
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
            "skipped": [c.name for c in self.checks if c.status == "skipped"],
            "unmeasured": [c.name for c in self.checks if c.status == "unmeasured"],
            "observed": [c.name for c in self.checks if c.status == "observed"],
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


#: Paths a declarative check may read. Validated so a typo fails the gate
#: (exit 2) instead of silently comparing `None` to a threshold.
_KNOWN_PATHS: frozenset[str] = frozenset({
    "runs.created", "runs.terminal", "runs.orphaned", "runs.active",
    "latency.p50", "latency.p95", "latency.p99", "latency.samples",
    "latency.ttft.p50", "latency.ttft.p95", "latency.ttft.p99", "latency.ttft.samples",
    "resume.p95", "resume.samples", "resume.successRate",
    "cost.perTaskP95", "cost.perTaskP50", "cost.samples", "cost.unpricedRuns",
    "model.attempts", "model.attemptsPerRun.p95", "model.fallbacks",
    "model.fallbackSuccessRate", "model.retries", "model.ttftTimeouts",
    "model.pricedCoverage",
    "context.overflow", "context.overflowRate", "context.recovered",
    "context.usageRatio.p95", "context.usageRatio.samples",
    "context.compactions.samples", "context.compactions.failures",
    "context.compactions.failureRate",
    "tools.batches.count", "tools.batches.orderingViolations",
    "tools.guardrails.halt",
    "goals.created", "goals.samples", "goals.completionRate", "goals.blockedRate",
    "goals.turns.p95",
    "learning.executionEvals.total", "learning.executionEvals.passed",
    "learning.executionEvals.failed", "learning.curator.runs",
    "integrity.effectUnknown", "integrity.leaseLost",
    "integrity.checkpointWriteFailures", "integrity.checkpointWriteP95Ms",
    "integrity.eventSeqRetries", "integrity.eventSeqCollisions",
    "integrity.toolBatchOrderingViolations", "integrity.skillEnabledWithoutEval",
    "integrity.hardlineBlocked",
    "fileCheckpoints.created", "fileCheckpoints.failed",
    "fileCheckpoints.restored", "fileCheckpoints.failureRate",
    "delegation.started", "delegation.completed", "delegation.failed",
    "delegation.completionRate",
})

_CHECK_KINDS = frozenset({"ratio", "percentile", "rate", "invariant"})


def _path(report: dict[str, Any], path: str) -> Any:
    node: Any = report
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _numeric(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _evaluate_spec(
    spec: dict[str, Any], report: dict[str, Any], baseline: dict[str, Any],
) -> GateCheck:
    if not isinstance(spec, dict):
        raise GateError("each checks[] entry must be an object")
    name = str(spec.get("name") or "").strip()
    path = str(spec.get("path") or "").strip()
    kind = str(spec.get("kind") or "").strip()
    if not name or not path or kind not in _CHECK_KINDS:
        raise GateError(f"invalid check spec: {spec!r}")
    if path not in _KNOWN_PATHS:
        raise GateError(f"unknown report path: {path}")
    enforced = bool(spec.get("enforce", True))
    requires = spec.get("requires")
    if requires and not bool((report.get("capabilities") or {}).get(str(requires))):
        return GateCheck(name, True, None, spec.get("target", spec.get("max")),
                         f"skipped: capability '{requires}' is off", status="skipped", enforced=enforced)
    samples_path = spec.get("samplesPath")
    samples = None
    if samples_path:
        if samples_path not in _KNOWN_PATHS:
            raise GateError(f"unknown samples path: {samples_path}")
        raw_samples = _path(report, samples_path)
        samples = int(raw_samples) if isinstance(raw_samples, (int, float)) else None
    min_samples = spec.get("minSamples")
    if min_samples is not None and samples is not None and samples < int(min_samples):
        if spec.get("requireSamples"):
            return GateCheck(name, False, None, spec.get("target", spec.get("max")),
                             f"unmeasured: {samples} sample(s), {int(min_samples)} required",
                             status="unmeasured", samples=samples, enforced=enforced)
        return GateCheck(name, True, None, spec.get("target", spec.get("max")),
                         f"skipped: {samples} sample(s), {int(min_samples)} required",
                         status="skipped", samples=samples, enforced=enforced)
    normalize = str(spec.get("normalize") or "")
    if normalize in ("terminal_over_created", "orphan_over_created"):
        created = _numeric(_path(report, "runs.created")) or 0.0
        numerator = _numeric(_path(report, "runs.terminal" if normalize.startswith("terminal") else "runs.orphaned")) or 0.0
        actual = None if created <= 0 else numerator / created
        if samples is None:
            samples = int(created)
    else:
        actual = _numeric(_path(report, path))
    if actual is None:
        if spec.get("requireSamples"):
            return GateCheck(name, False, None, spec.get("target", spec.get("max")),
                             "unmeasured: the report has no value", status="unmeasured",
                             samples=samples, enforced=enforced)
        return GateCheck(name, True, None, spec.get("target", spec.get("max")),
                         "skipped: the report has no value", status="skipped",
                         samples=samples, enforced=enforced)

    if kind == "ratio":
        target = float(spec.get("target", spec.get("min", 0.0)))
        ok, shown = actual >= target, target
        reason = ("within target" if ok else f"{actual:.4f} < target {target:.4f}")
    elif kind == "percentile":
        threshold = spec.get("thresholdMs", spec.get("threshold"))
        if threshold is None:
            raise GateError(f"{name}: percentile checks need thresholdMs")
        target = float(threshold)
        ok, shown = actual <= target, target
        reason = ("within budget" if ok else f"{actual:.4f} > {target:.4f}")
    elif kind == "rate":
        allowed = float(spec.get("max", spec.get("threshold", 0.0)))
        ok, shown = actual <= allowed, allowed
        reason = ("within budget" if ok else f"failure rate {actual:.4f} > {allowed:.4f}")
    else:  # invariant
        allowed = float(spec.get("max", 0.0))
        ok, shown = actual <= allowed, allowed
        reason = ("zero occurrences" if ok else f"{actual:.0f} occurrence(s), max {allowed:.0f}")

    check = GateCheck(
        name, ok, round(actual, 6), shown, reason,
        status="pass" if ok else "fail", samples=samples, enforced=enforced,
    )
    if not enforced:
        check.ok = True
        check.status = "observed"
        check.reason = f"observe only: {reason}"
        return check

    allowance = spec.get("maxRegression")
    baseline_value = _numeric(_path(baseline, str(spec.get("baselinePath") or path)))
    if allowance is not None and baseline_value is not None and baseline_value != 0 and ok:
        if kind == "ratio":
            allowed = baseline_value * (1.0 - float(allowance))
            regression_ok = actual >= allowed
        else:
            allowed = baseline_value * (1.0 + float(allowance))
            regression_ok = actual <= allowed
        if not regression_ok:
            check.ok = False
            check.status = "fail"
            check.reason = f"regressed vs baseline {baseline_value:.4f} (allowance {float(allowance) * 100:.1f}%)"
    return check


def _evaluate_checks(
    specs: Any, report: dict[str, Any], baseline: dict[str, Any],
) -> list[GateCheck]:
    if not isinstance(specs, list):
        raise GateError("budgets.checks must be a list")
    if not specs:
        raise GateError("budgets.checks must not be empty")
    return [_evaluate_spec(spec, report, baseline) for spec in specs]


def evaluate_gate(
    report: dict[str, Any],
    budgets: dict[str, Any],
    baseline: Optional[dict[str, Any]] = None,
) -> GateResult:
    """Evaluate declarative checks, or the legacy five-budget shape.

    A v2 file may carry `checks` and `budgets` together during the migration;
    both are evaluated. A missing sample is `skipped` unless the check says
    `requireSamples`, in which case it fails as `unmeasured`.
    """
    validate_report(report)
    baseline = baseline or {}
    specs = budgets.get("checks") if isinstance(budgets.get("checks"), list) else None
    declarative = _evaluate_checks(specs, report, baseline) if specs else []
    configured = budgets.get("budgets")
    if not isinstance(configured, dict) or not configured:
        if not specs:
            raise GateError("budgets.budgets must be a non-empty object")
        return GateResult(
            ok=all(check.ok for check in declarative), checks=declarative,
            reportGeneratedAt=report.get("generatedAt"),
        )
    checks: list[GateCheck] = list(declarative)

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
