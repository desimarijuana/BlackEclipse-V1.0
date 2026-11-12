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


def with_cost(run: dict[str, Any]) -> dict[str, Any]:
    """Attach `cost` to a run dict (non-destructive)."""
    out = dict(run)
    out["cost"] = estimate_run_cost(
        run.get("provider"),
        run.get("model"),
        int(run.get("promptTokens") or 0),
        int(run.get("completionTokens") or 0),
    )
    return out


__all__ = ["estimate_run_cost", "with_cost"]
