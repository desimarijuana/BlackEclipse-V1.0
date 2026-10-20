"""Deterministic production drift detection for the continual-learning loop.

Compares the most recent runs against the immediately preceding window. A drop
larger than the threshold with enough samples is `drift`; thin data is
`unmeasured`, never a fabricated zero. The result is a signal for an operator,
not an automatic change: a drift incident may open a scoped optimization, but it
never mutates the current harness by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

from ..evaluation.stats import wilson_interval

SUCCESS = "success"
FAILURE = "failure"
UNMEASURED = "unmeasured"
DRIFT = "drift"
STABLE = "stable"

_SUCCESS_STATUSES = frozenset({"completed", "success", "succeeded"})
_FAILURE_STATUSES = frozenset({"failed", "failure", "error", "errored"})


@dataclass(frozen=True)
class RunOutcome:
    runId: str
    agentId: str
    status: str
    createdAt: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _outcome_for_status(status: Any) -> Optional[str]:
    value = str(status or "").strip().lower()
    if value in _SUCCESS_STATUSES:
        return SUCCESS
    if value in _FAILURE_STATUSES:
        return FAILURE
    return None


def _rate_block(outcomes: list[str]) -> dict[str, Any]:
    total = len(outcomes)
    successes = sum(1 for outcome in outcomes if outcome == SUCCESS)
    low, high = wilson_interval(successes, total)
    return {
        "n": total,
        "successes": successes,
        "rate": (successes / total) if total else None,
        "ciLow": low,
        "ciHigh": high,
    }


def drift_signal(
    runs: Iterable[Mapping[str, Any] | RunOutcome],
    *,
    scope: str = "global",
    window: int = 30,
    baseline: int = 100,
    min_samples: int = 10,
    threshold: float = 0.10,
) -> dict[str, Any]:
    """Compare the newest `window` runs with the preceding `baseline` runs.

    `runs` must be newest-first. Cancelled/created/running rows are ignored.
    The signal is `unmeasured` when either side has fewer than `min_samples`
    terminal outcomes; `drift` only when the observed drop exceeds `threshold`.
    """
    cap_window = max(1, int(window))
    cap_baseline = max(1, int(baseline))
    min_n = max(1, int(min_samples))
    cap_threshold = max(0.0, float(threshold))

    resolved: list[RunOutcome] = []
    for row in runs:
        if isinstance(row, RunOutcome):
            resolved.append(row)
            continue
        outcome = _outcome_for_status(row.get("status"))
        if outcome is None:
            continue
        resolved.append(RunOutcome(
            runId=str(row.get("runId") or row.get("id") or ""),
            agentId=str(row.get("agentId") or ""),
            status=outcome,
            createdAt=str(row.get("createdAt") or ""),
        ))
    if scope and scope != "global":
        resolved = [row for row in resolved if row.agentId == scope]

    current_rows = resolved[:cap_window]
    baseline_rows = resolved[cap_window:cap_window + cap_baseline]
    current = _rate_block([row.status for row in current_rows])
    previous = _rate_block([row.status for row in baseline_rows])

    reasons: list[str] = []
    if current["n"] < min_n:
        reasons.append(f"current window has {current['n']} terminal run(s); need {min_n}")
    if previous["n"] < min_n:
        reasons.append(f"baseline window has {previous['n']} terminal run(s); need {min_n}")
    if reasons:
        return {
            "status": UNMEASURED,
            "scope": scope or "global",
            "window": cap_window,
            "baselineWindow": cap_baseline,
            "current": current,
            "baseline": previous,
            "drop": None,
            "threshold": cap_threshold,
            "reasons": reasons,
        }

    drop = round(float(previous["rate"]) - float(current["rate"]), 6)
    drifted = drop > cap_threshold
    if drifted:
        reasons.append(
            f"success rate dropped {drop:.3f} "
            f"({previous['rate']:.3f} → {current['rate']:.3f})"
        )
    else:
        reasons.append("no significant drop across the observed windows")
    return {
        "status": DRIFT if drifted else STABLE,
        "scope": scope or "global",
        "window": cap_window,
        "baselineWindow": cap_baseline,
        "current": current,
        "baseline": previous,
        "drop": drop,
        "threshold": cap_threshold,
        "reasons": reasons,
    }


def _store_runs(store: Any, *, scope: Optional[str], limit: int) -> list[dict[str, Any]]:
    if store is None:
        return []
    db = getattr(store, "_db", None)
    if db is not None:
        sql = (
            "SELECT id, agentId, status, createdAt FROM HarnessRun "
            "WHERE status IN ('completed','failed','error','cancelled') "
        )
        params: list[Any] = []
        if scope and scope != "global":
            sql += "AND agentId=? "
            params.append(scope)
        sql += "ORDER BY createdAt DESC LIMIT ?"
        params.append(max(1, min(int(limit), 2000)))
        try:
            return [
                {
                    "runId": row["id"], "agentId": row["agentId"],
                    "status": row["status"], "createdAt": row["createdAt"],
                }
                for row in db.execute(sql, params).fetchall()
            ]
        except Exception:  # noqa: BLE001 - an unreadable store is unmeasured
            return []
    try:
        rows = store.list_runs(limit=max(1, min(int(limit), 200)))
    except Exception:  # noqa: BLE001
        return []
    if scope and scope != "global":
        rows = [row for row in rows if row.get("agentId") == scope]
    return rows


def detect_store_drift(
    store: Any,
    *,
    scope: Optional[str] = None,
    window: int = 30,
    baseline: int = 100,
    min_samples: int = 10,
    threshold: float = 0.10,
) -> dict[str, Any]:
    """Read the bounded run history and return the drift signal."""
    limit = max(1, int(window) + int(baseline))
    runs = _store_runs(store, scope=scope, limit=limit)
    return drift_signal(
        runs, scope=scope or "global", window=window, baseline=baseline,
        min_samples=min_samples, threshold=threshold,
    )


__all__ = [
    "DRIFT",
    "FAILURE",
    "STABLE",
    "SUCCESS",
    "UNMEASURED",
    "RunOutcome",
    "detect_store_drift",
    "drift_signal",
]
