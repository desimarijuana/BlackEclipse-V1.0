"""Usage, cost, latency and budget tracking (spec §22–§25).

One `UsageRecord` per model request; normalized across providers. Token counts
that a provider did not supply are marked `estimated=True` — never presented as
exact. Pricing comes from the `PricingRegistry`; unknown pricing makes cost
`None`, never zero (zero would be a lie for a paid provider).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Optional

from .health import _percentile
from .registry import PricingRegistry
from .types import CostEstimate, ModelInfo, PricingKind, Usage


def _monotonic() -> float:
    return time.monotonic()


def extract_usage(message: Any) -> Usage:
    """Normalized usage from a LangChain response (or zeros, never invented)."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict):
        return Usage(
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            cached_tokens=int(
                (usage.get("input_token_details") or {}).get("cache_read") or 0
            ) if isinstance(usage.get("input_token_details"), dict) else 0,
            estimated=bool(usage.get("estimated")),
        )
    metadata = getattr(message, "response_metadata", None)
    if isinstance(metadata, dict):
        for key in ("token_usage", "usage"):
            raw = metadata.get(key)
            if isinstance(raw, dict):
                prompt = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
                completion = int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
                total = int(raw.get("total_tokens") or (prompt + completion))
                return Usage(
                    input_tokens=prompt,
                    output_tokens=completion,
                    total_tokens=total,
                    cached_tokens=int(raw.get("cached_tokens") or 0),
                )
    return Usage()


@dataclass
class UsageRecord:
    request_id: str
    provider_id: str
    model_id: str
    run_id: Optional[str] = None
    task: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    tokens_estimated: bool = False
    latency_ms: float = 0.0
    time_to_first_token_ms: Optional[float] = None
    success: bool = True
    error_class: Optional[str] = None
    retries: int = 0
    fallback: bool = False
    at: float = field(default_factory=lambda: time.time())
    cost: Optional[CostEstimate] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "requestId": self.request_id,
            "provider": self.provider_id,
            "model": self.model_id,
            "runId": self.run_id,
            "task": self.task,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cachedTokens": self.cached_tokens,
            "totalTokens": self.total_tokens,
            "tokensEstimated": self.tokens_estimated,
            "latencyMs": self.latency_ms,
            "timeToFirstTokenMs": self.time_to_first_token_ms,
            "success": self.success,
            "errorClass": self.error_class,
            "retries": self.retries,
            "fallback": self.fallback,
            "at": self.at,
            "cost": self.cost.to_dict() if self.cost else None,
        }


class CostTracker:
    """Compute and accumulate cost from the pricing registry (spec §23)."""

    def __init__(self, pricing: PricingRegistry) -> None:
        self._pricing = pricing
        self._total: dict[str, float] = {}
        self._unknown_requests = 0

    def estimate(self, model: ModelInfo, usage: Usage) -> Optional[CostEstimate]:
        pricing = self._pricing.pricing_for(model)
        if pricing.kind is PricingKind.FREE:
            return CostEstimate(
                input_cost=0.0, output_cost=0.0, cached_input_cost=0.0,
                total_cost=0.0, kind="free", estimated=False, basis="free (local)",
            )
        if pricing.kind is PricingKind.UNKNOWN:
            self._unknown_requests += 1
            return None
        if pricing.kind is PricingKind.PER_REQUEST:
            return CostEstimate(
                total_cost=pricing.per_request,
                currency=pricing.currency,
                kind="per_request",
                estimated=False,
                basis=pricing.source or "declared per-request",
            )
        if pricing.kind is PricingKind.CUSTOM:
            return None
        # PER_TOKEN
        if pricing.input_per_million is None and pricing.output_per_million is None:
            self._unknown_requests += 1
            return None
        input_cost = None
        output_cost = None
        cached_cost = None
        if pricing.input_per_million is not None:
            uncached = max(0, usage.input_tokens - usage.cached_tokens)
            input_cost = (uncached / 1_000_000.0) * pricing.input_per_million
            if pricing.cached_input_per_million is not None and usage.cached_tokens:
                cached_cost = (usage.cached_tokens / 1_000_000.0) * pricing.cached_input_per_million
        if pricing.output_per_million is not None:
            output_cost = (usage.output_tokens / 1_000_000.0) * pricing.output_per_million
        total = sum(v for v in (input_cost, output_cost, cached_cost) if v is not None)
        return CostEstimate(
            input_cost=input_cost,
            output_cost=output_cost,
            cached_input_cost=cached_cost,
            total_cost=total,
            currency=pricing.currency,
            kind="per_token",
            estimated=usage.estimated,
            basis=pricing.source or "declared per-token",
        )

    def record(self, model: ModelInfo, cost: Optional[CostEstimate]) -> None:
        if cost is None or cost.total_cost is None:
            return
        self._total[model.provider_id] = self._total.get(model.provider_id, 0.0) + cost.total_cost
        self._total["__all__"] = self._total.get("__all__", 0.0) + cost.total_cost

    def total(self, key: str = "__all__") -> float:
        return round(self._total.get(key, 0.0), 6)

    @property
    def unknown_requests(self) -> int:
        return self._unknown_requests


class LatencyTracker:
    """Track TTFT and total latency percentiles (spec §25)."""

    def __init__(self, *, window: int = 200) -> None:
        self._total: dict[str, Deque[float]] = {}
        self._ttft: dict[str, Deque[float]] = {}
        self._window = window

    def record(self, key: str, *, total_ms: float, ttft_ms: Optional[float] = None) -> None:
        self._total.setdefault(key, deque(maxlen=self._window)).append(total_ms)
        if ttft_ms is not None:
            self._ttft.setdefault(key, deque(maxlen=self._window)).append(ttft_ms)

    def last_latency_ms(self, key: str) -> Optional[float]:
        values = self._total.get(key)
        return values[-1] if values else None

    def total_percentiles(self, key: str) -> dict[str, Optional[float]]:
        values = list(self._total.get(key, ()))
        if not values:
            return {"p50": None, "p90": None, "p95": None, "p99": None}
        return {
            "p50": _percentile(values, 50),
            "p90": _percentile(values, 90),
            "p95": _percentile(values, 95),
            "p99": _percentile(values, 99),
        }

    def ttft_percentiles(self, key: str) -> dict[str, Optional[float]]:
        values = list(self._ttft.get(key, ()))
        if not values:
            return {"p50": None, "p95": None}
        return {"p50": _percentile(values, 50), "p95": _percentile(values, 95)}

    def snapshot(self, key: str) -> dict[str, Any]:
        return {
            "key": key,
            "total": self.total_percentiles(key),
            "ttft": self.ttft_percentiles(key),
            "lastLatencyMs": self.last_latency_ms(key),
        }


@dataclass
class Budget:
    key: str
    amount: float
    period: str = "daily"  # daily | monthly | total
    spent: float = 0.0

    @property
    def remaining(self) -> float:
        return max(0.0, self.amount - self.spent)

    @property
    def pressure(self) -> float:
        """0..1 fraction of the budget consumed (1.0 = exhausted)."""
        if self.amount <= 0:
            return 1.0
        return min(1.0, self.spent / self.amount)


class BudgetManager:
    """Budgets at multiple levels (spec §24).

    Keys are free-form: `global`, `provider:openai`, `model:openai/gpt-4o`,
    `agent:research`, `workflow:x`, `task:y`, `user:z`, `session:z`, plus a
    `:daily` / `:monthly` suffix. The router reads `pressure(key)` to downgrade
    from premium → cheap → free as a budget fills.
    """

    def __init__(self) -> None:
        self._budgets: dict[str, Budget] = {}

    def set_budget(self, key: str, amount: float, *, period: str = "daily") -> None:
        existing = self._budgets.get(key)
        spent = existing.spent if existing else 0.0
        self._budgets[key] = Budget(key=key, amount=amount, period=period, spent=spent)

    def get(self, key: str) -> Optional[Budget]:
        return self._budgets.get(key)

    def record(self, key: str, cost: Optional[float]) -> None:
        if cost is None:
            return
        budget = self._budgets.get(key)
        if budget is not None:
            budget.spent += cost

    def pressure(self, keys: list[str]) -> float:
        """The maximum pressure across the budget keys that exist (0 if none)."""
        values = [self._budgets[k].pressure for k in keys if k in self._budgets]
        return max(values) if values else 0.0

    def exceeded(self, keys: list[str]) -> bool:
        return any(self._budgets[k].pressure >= 1.0 for k in keys if k in self._budgets)

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {"key": b.key, "amount": b.amount, "spent": round(b.spent, 6),
             "remaining": round(b.remaining, 6), "period": b.period, "pressure": round(b.pressure, 4)}
            for b in self._budgets.values()
        ]


class UsageStore:
    """Accumulates usage records and fans them out to a persistence sink.

    The sink is injected (a callable taking a `UsageRecord`) so the runtime has
    no hard dependency on the harness database. `_sink` failures never break a
    model call — usage accounting is advisory.
    """

    def __init__(
        self,
        *,
        size: int = 500,
        sink: Optional[Callable[[UsageRecord], None]] = None,
    ) -> None:
        self._records: Deque[UsageRecord] = deque(maxlen=size)
        self._sink = sink
        self._count = 0

    def set_sink(self, sink: Optional[Callable[[UsageRecord], None]]) -> None:
        self._sink = sink

    def record(self, record: UsageRecord) -> None:
        self._records.append(record)
        self._count += 1
        if self._sink is not None:
            try:
                self._sink(record)
            except Exception:  # noqa: BLE001 - accounting must never break a run
                pass

    def recent(self, limit: int = 100) -> list[UsageRecord]:
        return list(self._records)[-limit:]

    @property
    def count(self) -> int:
        return self._count

    def summary(self) -> dict[str, Any]:
        records = list(self._records)
        prompt = sum(r.input_tokens for r in records)
        completion = sum(r.output_tokens for r in records)
        total = sum(r.total_tokens for r in records)
        cost = sum(
            (r.cost.total_cost or 0.0) for r in records if r.cost and r.cost.total_cost is not None
        )
        succeeded = sum(1 for r in records if r.success)
        latencies = [r.latency_ms for r in records if r.latency_ms > 0]
        return {
            "requests": len(records),
            "successful": succeeded,
            "failed": len(records) - succeeded,
            "inputTokens": prompt,
            "outputTokens": completion,
            "totalTokens": total,
            "estimatedCost": round(cost, 6),
            "averageLatencyMs": round(sum(latencies) / len(latencies), 2) if latencies else None,
        }


__all__ = [
    "Budget",
    "BudgetManager",
    "CostTracker",
    "LatencyTracker",
    "UsageRecord",
    "UsageStore",
]
