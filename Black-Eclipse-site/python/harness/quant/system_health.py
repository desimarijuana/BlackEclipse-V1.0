"""One health view for the operator: data, broker, risk, runner, lifecycle.

The score is a summary of named checks. It is not a trading signal and it is not
a substitute for the underlying report. Every failing check names its reason.
"""

from __future__ import annotations

from typing import Any


def health(
    *,
    data_quality: dict[str, Any] | None = None,
    broker: dict[str, Any] | None = None,
    risk: dict[str, Any] | None = None,
    runner: dict[str, Any] | None = None,
    lifecycle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    unknown: list[str] = []

    def add(name: str, ok: bool, detail: str, *, critical: bool = True) -> None:
        checks.append({"check": name, "passed": bool(ok), "detail": detail,
                       "critical": critical})

    if data_quality is None:
        add("data", True, "not checked", critical=False)
        unknown.append("data")
    else:
        gate = data_quality.get("gate") or {}
        add("data", bool(gate.get("allowed")),
            "; ".join(gate.get("reasons") or []) or "clean")

    if broker is None:
        add("broker", True, "not checked", critical=False)
        unknown.append("broker")
    else:
        mode = str(broker.get("mode") or "unknown")
        status = str(broker.get("status") or "unknown")
        add("broker", status == "connected",
            f"{mode} · {status}")

    if risk is None:
        add("risk", True, "not checked", critical=False)
        unknown.append("risk")
    else:
        kill = risk.get("kill") or {}
        allowed = risk.get("allowed")
        add("risk", bool(allowed) and not kill.get("triggered"),
            "; ".join(risk.get("reasons") or kill.get("reasons") or []) or "clear")

    if runner is None:
        add("runner", True, "runner not requested", critical=False)
    else:
        add("runner", runner.get("state") != "failed",
            str(runner.get("state") or "unknown"))

    if lifecycle is None:
        add("lifecycle", True, "no lifecycle row", critical=False)
    else:
        state = str(lifecycle.get("state") or "draft")
        add("lifecycle", state not in ("retired",),
            state, critical=False)

    failed = [c for c in checks if c["critical"] and not c["passed"]]
    total = len(checks)
    passed = sum(1 for c in checks if c["passed"])
    score = round(100 * passed / total) if total else 0
    status = "BLOCKED" if failed else ("DEGRADED" if unknown else "OK")
    return {
        "status": status,
        "score": score,
        "checks": checks,
        "blockers": [c["detail"] for c in failed],
        "unknown": unknown,
        "note": "A blocked system must not send a new live order.",
    }


__all__ = ["health"]
