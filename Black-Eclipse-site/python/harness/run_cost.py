"""Per-run dollar cost from the one pricing authority.

Costs are derived from the recorded provider/model and token counts. An unknown
model returns `costUsd: None` with `priced: false` — never a fabricated zero.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from .observability.costs import CostEngine


@lru_cache(maxsize=1)
def _engine() -> CostEngine:
    return CostEngine()


def estimate_run_cost(
    provider: Optional[str],
    model: Optional[str],
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    try:
        breakdown, tokens = _engine().compute(
            provider=provider,
            model=model,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(completion_tokens or 0),
            total_tokens=int(prompt_tokens or 0) + int(completion_tokens or 0),
        )
    except Exception:  # noqa: BLE001 - cost must never break a run read
        return {"costUsd": None, "priced": False, "currency": "USD", "tokens": {}}
    return {
        "costUsd": round(breakdown.total_cost, 8) if breakdown.priced else None,
        "priced": bool(breakdown.priced),
        "currency": breakdown.currency,
        "inputCost": round(breakdown.input_cost, 8) if breakdown.input_cost is not None else None,
        "outputCost": round(breakdown.output_cost, 8) if breakdown.output_cost is not None else None,
        "tokens": tokens,
    }


def estimate_run_cost_from_attempts(store: Any, run_id: str) -> Optional[dict[str, Any]]:
    """Cost/tokens from the physical `ModelRequest` rows for one run.

    Returns None when the store/table/rows are absent, so the caller can fall
    back to the final-response estimate. An unpriced attempt makes the aggregate
    unpriced — never a fabricated zero.
    """
    db = getattr(store, "_db", None) if store is not None else None
    if db is None:
        return None
    try:
        rows = db.execute(
            "SELECT inputTokens, outputTokens, totalTokens, costTotal, costEstimated "
            "FROM ModelRequest WHERE runId=?",
            (run_id,),
        ).fetchall()
    except Exception:  # noqa: BLE001 - older DB / test double
        return None
    if not rows:
        return None
    input_tokens = sum(int(r["inputTokens"] or 0) for r in rows)
    output_tokens = sum(int(r["outputTokens"] or 0) for r in rows)
    total_tokens = sum(int(r["totalTokens"] or 0) for r in rows)
    # A failed 429/401 attempt that consumed no tokens is zero spend, not
    # "unknown price". Only attempts with tokens (or a declared cost) price the
    # aggregate.
    cost_rows = [
        r for r in rows
        if int(r["totalTokens"] or 0) > 0 or r["costTotal"] is not None
    ]
    priced_rows = [r for r in cost_rows if r["costTotal"] is not None]
    priced = bool(cost_rows) and len(priced_rows) == len(cost_rows)
    cost_usd = round(sum(float(r["costTotal"]) for r in priced_rows), 8) if priced else None
    return {
        "costUsd": cost_usd,
        "priced": priced,
        "currency": "USD",
        "attempts": len(rows),
        "pricedAttempts": len(priced_rows),
        "costedAttempts": len(cost_rows),
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
        "estimated": any(int(r["costEstimated"] or 0) for r in rows),
        "source": "model_attempts",
    }


def with_cost(run: dict[str, Any], store: Any = None) -> dict[str, Any]:
    """Attach `cost` to a run dict (non-destructive).

    Prefer the physical-attempt ledger when it exists: failed attempts and
    fallbacks are real spend and must be visible. Fall back to the historical
    final-token estimate for older runs.
    """
    out = dict(run)
    attempt_cost = estimate_run_cost_from_attempts(store, str(run.get("id") or ""))
    if attempt_cost is not None:
        out["cost"] = attempt_cost
        return out
    out["cost"] = estimate_run_cost(
        run.get("provider"),
        run.get("model"),
        int(run.get("promptTokens") or 0),
        int(run.get("completionTokens") or 0),
    )
    return out


__all__ = [
    "estimate_run_cost",
    "estimate_run_cost_from_attempts",
    "with_cost",
]
