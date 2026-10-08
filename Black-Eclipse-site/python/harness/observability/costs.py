"""Token & cost engine — the ONE canonical place model usage becomes money.

Every LLM observation (from the model runtime's observer events or from derived
run events) is normalized through `CostEngine.record`, which computes input /
output / cached / total cost from a `PricingRegistry` and folds the result into
rolling aggregates by run, session, agent, task, workflow, model, provider, day
and month.

Pricing is DATA, never code scattered through the app: built-in defaults cover
the common catalog, and a deployment can override or extend them with a JSON file
(`ECLIPSE_PRICING_FILE`) or programmatic `register`. An unknown model yields
`None` cost — honestly unknown, never a fabricated zero.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("harness.observability.costs")

# (provider-substring-or-model-substring) -> (input, output, cached) USD per 1M tokens
_DEFAULT_PRICING: dict[str, tuple[float, float, float]] = {
    "gpt-4o-mini": (0.15, 0.60, 0.075),
    "gpt-4o": (2.50, 10.00, 1.25),
    "gpt-4.1": (2.00, 8.00, 0.50),
    "gpt-4.1-mini": (0.40, 1.60, 0.10),
    "o1": (15.00, 60.00, 7.50),
    "o3": (2.00, 8.00, 0.50),
    "o4-mini": (1.10, 4.40, 0.275),
    "claude-3-5-sonnet": (3.00, 15.00, 0.30),
    "claude-3-7-sonnet": (3.00, 15.00, 0.30),
    "claude-sonnet-4": (3.00, 15.00, 0.30),
    "claude-opus-4": (15.00, 75.00, 1.50),
    "claude-3-5-haiku": (0.80, 4.00, 0.08),
    "gemini-2.5-pro": (1.25, 10.00, 0.31),
    "gemini-2.5-flash": (0.30, 2.50, 0.075),
    "gemini-2.0-flash": (0.10, 0.40, 0.025),
    "deepseek-chat": (0.27, 1.10, 0.07),
    "deepseek-reasoner": (0.55, 2.19, 0.14),
    "mistral-large": (2.00, 6.00, 1.00),
    "llama-3.3-70b": (0.59, 0.79, 0.00),
    "llama-3.1-8b": (0.05, 0.08, 0.00),
    "grok-3": (3.00, 15.00, 0.75),
}


@dataclass
class Pricing:
    input_per_million: Optional[float] = None
    output_per_million: Optional[float] = None
    cached_input_per_million: Optional[float] = None
    reasoning_per_million: Optional[float] = None
    currency: str = "USD"

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputPerMillion": self.input_per_million,
            "outputPerMillion": self.output_per_million,
            "cachedInputPerMillion": self.cached_input_per_million,
            "reasoningPerMillion": self.reasoning_per_million,
            "currency": self.currency,
        }


@dataclass
class CostBreakdown:
    input_cost: Optional[float] = None
    output_cost: Optional[float] = None
    cached_cost: Optional[float] = None
    reasoning_cost: Optional[float] = None
    total_cost: Optional[float] = None
    currency: str = "USD"
    priced: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "inputCost": _round(self.input_cost),
            "outputCost": _round(self.output_cost),
            "cachedCost": _round(self.cached_cost),
            "reasoningCost": _round(self.reasoning_cost),
            "totalCost": _round(self.total_cost),
            "currency": self.currency,
            "priced": self.priced,
        }


def _round(value: Optional[float]) -> Optional[float]:
    return None if value is None else round(value, 8)


def _normalize(pricing: Pricing) -> dict[str, float]:
    return {
        "input": pricing.input_per_million or 0.0,
        "output": pricing.output_per_million or 0.0,
        "cached": pricing.cached_input_per_million or 0.0,
        "reasoning": pricing.reasoning_per_million or 0.0,
    }


class PricingRegistry:
    def __init__(self) -> None:
        self._exact: dict[str, Pricing] = {}
        self._substrings: dict[str, Pricing] = {}
        for needle, (i, o, c) in _DEFAULT_PRICING.items():
            self._substrings[needle.lower()] = Pricing(i, o, c)
        self._load_file(os.environ.get("ECLIPSE_PRICING_FILE", ""))

    def _load_file(self, path: str) -> None:
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - a bad pricing file must not break boot
            log.warning("pricing file unreadable (%s): %s", path, exc)
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(value, dict):
                continue
            try:
                self._exact[str(key).lower()] = Pricing(
                    input_per_million=_opt(value.get("input") if "input" in value else value.get("inputPerMillion")),
                    output_per_million=_opt(value.get("output") if "output" in value else value.get("outputPerMillion")),
                    cached_input_per_million=_opt(value.get("cached") if "cached" in value else value.get("cachedInputPerMillion")),
                    reasoning_per_million=_opt(value.get("reasoning") if "reasoning" in value else value.get("reasoningPerMillion")),
                    currency=str(value.get("currency", "USD")),
                )
            except Exception:  # noqa: BLE001
                continue

    def register(self, model: str, pricing: Pricing) -> None:
        """Register an EXACT pricing entry (highest precedence)."""
        self._exact[model.lower()] = pricing

    def pricing_for(self, provider: Optional[str], model: Optional[str]) -> Optional[Pricing]:
        candidates = [c for c in (model, f"{provider}/{model}" if provider and model else None, provider) if c]
        for candidate in candidates:
            key = candidate.lower()
            if key in self._exact:
                return self._exact[key]
        for candidate in candidates:
            key = candidate.lower()
            for needle, pricing in self._substrings.items():
                if needle in key:
                    return pricing
        return None


def _opt(value: Any) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class _Agg:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    unpriced: int = 0

    def add(self, tokens: dict[str, int], cost: float, priced: bool) -> None:
        self.requests += 1
        self.input_tokens += int(tokens.get("input", 0))
        self.output_tokens += int(tokens.get("output", 0))
        self.cached_tokens += int(tokens.get("cached", 0))
        self.reasoning_tokens += int(tokens.get("reasoning", 0))
        self.total_tokens += int(tokens.get("total", 0) or (tokens.get("input", 0) + tokens.get("output", 0)))
        if priced:
            self.cost += cost
        else:
            self.unpriced += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "inputTokens": self.input_tokens,
            "outputTokens": self.output_tokens,
            "cachedTokens": self.cached_tokens,
            "reasoningTokens": self.reasoning_tokens,
            "totalTokens": self.total_tokens,
            "cost": round(self.cost, 8),
            "costKnown": self.unpriced == 0,
            "unpricedRequests": self.unpriced,
        }


class CostEngine:
    def __init__(self, *, pricing: Optional[PricingRegistry] = None) -> None:
        self.pricing = pricing or PricingRegistry()
        self._lock = threading.RLock()
        self._by_run: dict[str, _Agg] = defaultdict(_Agg)
        self._by_session: dict[str, _Agg] = defaultdict(_Agg)
        self._by_agent: dict[str, _Agg] = defaultdict(_Agg)
        self._by_task: dict[str, _Agg] = defaultdict(_Agg)
        self._by_workflow: dict[str, _Agg] = defaultdict(_Agg)
        self._by_model: dict[str, _Agg] = defaultdict(_Agg)
        self._by_provider: dict[str, _Agg] = defaultdict(_Agg)
        self._by_day: dict[str, _Agg] = defaultdict(_Agg)
        self._by_month: dict[str, _Agg] = defaultdict(_Agg)
        self._total = _Agg()

    def compute(
        self,
        *,
        provider: Optional[str],
        model: Optional[str],
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        total_tokens: Optional[int] = None,
    ) -> tuple[CostBreakdown, dict[str, int]]:
        pricing = self.pricing.pricing_for(provider, model)
        tokens = {
            "input": int(input_tokens),
            "output": int(output_tokens),
            "cached": int(cached_tokens),
            "reasoning": int(reasoning_tokens),
            "total": int(total_tokens or (input_tokens + output_tokens)),
        }
        if pricing is None:
            return CostBreakdown(priced=False), tokens
        rates = _normalize(pricing)
        # Cached tokens are a SUBSET of input tokens in most providers; price the
        # cached portion at the cache rate and the remainder at the input rate.
        uncached_input = max(0, tokens["input"] - tokens["cached"])
        input_cost = uncached_input / 1_000_000 * rates["input"]
        cached_cost = tokens["cached"] / 1_000_000 * rates["cached"]
        output_cost = tokens["output"] / 1_000_000 * rates["output"]
        reasoning_cost = tokens["reasoning"] / 1_000_000 * rates["reasoning"]
        total = input_cost + cached_cost + output_cost + reasoning_cost
        return (
            CostBreakdown(
                input_cost=input_cost,
                output_cost=output_cost,
                cached_cost=cached_cost,
                reasoning_cost=reasoning_cost,
                total_cost=total,
                currency=pricing.currency,
                priced=True,
            ),
            tokens,
        )

    def record(
        self,
        *,
        provider: Optional[str],
        model: Optional[str],
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        total_tokens: Optional[int] = None,
        run_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
    ) -> CostBreakdown:
        breakdown, tokens = self.compute(
            provider=provider, model=model,
            input_tokens=input_tokens, output_tokens=output_tokens,
            cached_tokens=cached_tokens, reasoning_tokens=reasoning_tokens,
            total_tokens=total_tokens,
        )
        cost = breakdown.total_cost or 0.0
        now = datetime.now(timezone.utc)
        key_model = f"{provider}/{model}" if provider and model else (model or provider or "unknown")
        with self._lock:
            self._total.add(tokens, cost, breakdown.priced)
            self._by_model[key_model].add(tokens, cost, breakdown.priced)
            self._by_provider[(provider or "unknown")].add(tokens, cost, breakdown.priced)
            self._by_day[now.strftime("%Y-%m-%d")].add(tokens, cost, breakdown.priced)
            self._by_month[now.strftime("%Y-%m")].add(tokens, cost, breakdown.priced)
            for store, key in (
                (self._by_run, run_id),
                (self._by_session, session_id),
                (self._by_agent, agent_id),
                (self._by_task, task_id),
                (self._by_workflow, workflow_id),
            ):
                if key:
                    store[key].add(tokens, cost, breakdown.priced)
        return breakdown

    # ── read models ─────────────────────────────────────────────────────────
    def run_cost(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            return self._by_run.get(run_id, _Agg()).to_dict()

    def summary(self, *, top: int = 20) -> dict[str, Any]:
        with self._lock:
            def top_items(store: dict[str, _Agg]) -> list[dict[str, Any]]:
                items = sorted(store.items(), key=lambda kv: kv[1].cost, reverse=True)[:top]
                return [{"key": k, **v.to_dict()} for k, v in items]

            return {
                "total": self._total.to_dict(),
                "byModel": top_items(self._by_model),
                "byProvider": top_items(self._by_provider),
                "byAgent": top_items(self._by_agent),
                "byDay": top_items(self._by_day),
                "byMonth": top_items(self._by_month),
                "runsTracked": len(self._by_run),
                "sessionsTracked": len(self._by_session),
            }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "total": self._total.to_dict(),
                "runs": {k: v.to_dict() for k, v in self._by_run.items()},
                "models": {k: v.to_dict() for k, v in self._by_model.items()},
                "providers": {k: v.to_dict() for k, v in self._by_provider.items()},
                "days": {k: v.to_dict() for k, v in self._by_day.items()},
            }

    def reset(self) -> None:
        with self._lock:
            self._by_run.clear()
            self._by_session.clear()
            self._by_agent.clear()
            self._by_task.clear()
            self._by_workflow.clear()
            self._by_model.clear()
            self._by_provider.clear()
            self._by_day.clear()
            self._by_month.clear()
            self._total = _Agg()


__all__ = ["CostEngine", "PricingRegistry", "Pricing", "CostBreakdown"]
