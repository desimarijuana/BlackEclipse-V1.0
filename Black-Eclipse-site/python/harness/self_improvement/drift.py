"""Deterministic production drift detection for the continual-learning loop.

Compares the most recent runs against the immediately preceding window. A drop
larger than the threshold with enough samples is `drift`; thin data is
`unmeasured`, never a fabricated zero. The result is a signal for an operator,
not an automatic change: a drift incident may open a scoped optimization, but it
never mutates the current harness by itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Optional

from ..code.evolution_store import EvolutionStore
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
    anchor = (
        current_rows[0].runId or current_rows[0].createdAt
        if current_rows else None
    )

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
            "anchor": anchor,
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
        "anchor": anchor,
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


def drift_history(
    store: Any,
    *,
    scope: Optional[str] = None,
    window: int = 30,
    baseline: int = 100,
    min_samples: int = 10,
    threshold: float = 0.10,
    limit: int = 12,
    step: Optional[int] = None,
    offset: int = 0,
) -> dict[str, Any]:
    """Compute the drift signal at successive points in the same run history.

    Point zero is the current window. Each later point moves `step` runs back
    (default: one window), so the result is a deterministic, read-only history
    over existing runs rather than a separate signal log. Thin points stay
    `unmeasured`; no rate is fabricated.
    """
    cap_window = max(1, int(window))
    cap_baseline = max(1, int(baseline))
    cap_limit = max(1, min(int(limit), 50))
    cap_step = max(1, int(step or cap_window))
    cap_offset = max(0, int(offset))
    needed = cap_window + cap_baseline + cap_step * (cap_limit - 1)
    max_runs = 2000
    runs = _store_runs(store, scope=scope, limit=min(needed + cap_offset, max_runs))
    resolved_scope = scope or "global"

    points: list[dict[str, Any]] = []
    for index in range(cap_limit):
        point_offset = cap_offset + index * cap_step
        sliced = runs[point_offset:point_offset + cap_window + cap_baseline]
        signal = drift_signal(
            sliced, scope=resolved_scope, window=cap_window,
            baseline=cap_baseline, min_samples=min_samples,
            threshold=threshold,
        )
        points.append({
            "offset": point_offset,
            "at": sliced[0].get("createdAt") if sliced else None,
            "status": signal["status"],
            "drop": signal["drop"],
            "current": signal["current"],
            "baseline": signal["baseline"],
        })
        if len(sliced) < cap_window + cap_baseline:
            break

    return {
        "scope": resolved_scope,
        "window": cap_window,
        "baselineWindow": cap_baseline,
        "threshold": max(0.0, float(threshold)),
        "step": cap_step,
        "offset": cap_offset,
        "requestedPoints": cap_limit,
        "computedPoints": len(points),
        "truncated": needed > max_runs or len(points) < cap_limit,
        "points": points,
    }


def drift_signature(signal: Mapping[str, Any]) -> str:
    """One drift episode identity: scope + window policy, not the noisy rate."""
    raw = json.dumps({
        "scope": signal.get("scope") or "global",
        "window": signal.get("window"),
        "baselineWindow": signal.get("baselineWindow"),
        "threshold": signal.get("threshold"),
        "anchor": signal.get("anchor"),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def record_drift_candidate(store: Any, signal: Mapping[str, Any]) -> dict[str, Any]:
    """Materialize an inert `drift` candidate for a detected regression.

    The candidate has no target or operations: a drift signal is evidence, not a
    patch. The operator can inspect it, stage ops, run the model proposer, or use
    a surface experiment; verification/landing stay the existing paths. One
    candidate per scope/window/threshold episode is deduplicated by signature.
    """
    if store is None:
        return {"created": False, "reason": "store_unavailable", "candidate": None}
    if str(signal.get("status") or "") != DRIFT:
        return {
            "created": False,
            "reason": f"signal is {signal.get('status') or UNMEASURED}",
            "candidate": None,
        }
    evolution = EvolutionStore(store)
    signature = drift_signature(signal)
    existing = evolution.get_by_signature(signature)
    if existing is not None:
        return {"created": False, "reason": "already_exists", "candidate": existing}

    scope = str(signal.get("scope") or "global")
    drop = signal.get("drop")
    current = signal.get("current") or {}
    baseline = signal.get("baseline") or {}
    problem = (
        f"Production success for {scope} dropped {drop} over the last "
        f"{signal.get('window')} terminal runs "
        f"({current.get('successes')}/{current.get('n')} vs "
        f"{baseline.get('successes')}/{baseline.get('n')} in the preceding window)."
    )[:1000]
    candidate = evolution.save_candidate({
        "signature": signature,
        "sourceCategory": "drift",
        "observedCount": int(current.get("n") or 1),
        "problemStatement": problem,
        "targetPath": None,
        "proposedOps": None,
        "subjectType": "drift",
        "scope": scope,
        "status": "inert",
    })
    return {"created": True, "reason": "drift", "candidate": candidate}


__all__ = [
    "DRIFT",
    "FAILURE",
    "STABLE",
    "SUCCESS",
    "UNMEASURED",
    "RunOutcome",
    "detect_store_drift",
    "drift_history",
    "drift_signal",
    "drift_signature",
    "record_drift_candidate",
]
