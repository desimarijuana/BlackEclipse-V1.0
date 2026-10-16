"""Run-level collection of the portfolio computations an answer rested on.

The Fiduciary Gate (`advisory.gate`) can only verify a recommendation against a
computation the run ACTUALLY performed. This collector is that record: every
`portfolio_*` tool call hands its canonical inputs and structured result here,
and the gate reads it at the answer seam.

It is a DERIVED read model, exactly like `SourceCollector`: best-effort, never
raises, never changes a tool's result or the run's authorization. A tool that
returns nothing structured simply contributes no computation.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Tools whose output is a genuine COMPUTATION (the engine solved/produced a
# number). Everything else that starts with `portfolio_` is a read/consult.
_COMPUTE_PREFIXES: tuple[str, ...] = (
    "portfolio_calculate_",
    "portfolio_rebalance",
    "portfolio_construct",
    "portfolio_optimize",
    "portfolio_estimate_",
    "portfolio_risk_",
    "portfolio_stress_",
    "portfolio_attribution",
    "portfolio_hedge",
    "portfolio_simulate_",
    "portfolio_compare_",
    "portfolio_factor_",
    "portfolio_transaction_costs",
)

_READ_TOOLS = frozenset({"portfolio_get", "portfolio_list", "portfolio_list_runs",
                         "portfolio_get_run", "portfolio_list_reconciliations"})

_SYMBOL_KEYS = frozenset({"symbol", "ticker", "symbols", "asset", "instrument",
                          "assetid", "instrumentid"})
_ACTION_KEYS = frozenset({"action", "side", "txntype", "type", "recommendation",
                          "direction"})

_TICKER_RE = re.compile(r"\$?\b([A-Z]{1,6}(?:[.\-][A-Z0-9]{1,3})?)\b")


def is_compute_tool(tool_name: str) -> bool:
    if tool_name in _READ_TOOLS:
        return False
    return tool_name.startswith(_COMPUTE_PREFIXES)


class AdvisoryCollector:
    """Accumulates the run's portfolio computations and consulted symbols."""

    def __init__(self) -> None:
        self._computations: list[dict[str, Any]] = []
        self._consulted: set[str] = set()
        self._seen: set[tuple[Any, ...]] = set()

    # ── Ingestion ───────────────────────────────────────────────────────────
    def add(self, tool_name: str, args: dict[str, Any], data: Any) -> None:
        """Record one tool call. Never raises — collection is best-effort."""
        try:
            name = str(tool_name)
            if not name.startswith("portfolio_"):
                return
            symbols = _collect_symbols(data) | _symbol_args(args)
            self._consulted.update(symbols)
            key = (name, _arg_str(args, "portfolio_id", "portfolioId"),
                   tuple(sorted(symbols)), tuple(_collect_numbers(data)))
            if key in self._seen:
                return
            self._seen.add(key)
            self._computations.append({
                "tool": name,
                "compute": is_compute_tool(name),
                "portfolioId": _arg_str(args, "portfolio_id", "portfolioId"),
                "symbols": sorted(symbols),
                "numbers": _collect_numbers(data),
                "actions": _collect_actions(data),
            })
        except Exception:  # noqa: BLE001 - collection must never break a run
            return

    # ── Output ──────────────────────────────────────────────────────────────
    def computations(self) -> list[dict[str, Any]]:
        return list(self._computations)

    def consulted_symbols(self) -> set[str]:
        return set(self._consulted)

    def portfolio_id(self) -> Optional[str]:
        """The first portfolio a computation/consult named, or None."""
        for comp in self._computations:
            if comp.get("portfolioId"):
                return str(comp["portfolioId"])
        return None

    def has_content(self) -> bool:
        return bool(self._computations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "computations": self.computations(),
            "consultedSymbols": sorted(self._consulted),
        }


# ── walkers ───────────────────────────────────────────────────────────────────
def _arg_str(args: Any, *names: str) -> Optional[str]:
    if not isinstance(args, dict):
        return None
    for name in names:
        value = args.get(name)
        if value:
            return str(value)
    return None


def _symbol_args(args: Any) -> set[str]:
    out: set[str] = set()
    if not isinstance(args, dict):
        return out
    for key in ("symbol", "symbols", "ticker"):
        value = args.get(key)
        if isinstance(value, str) and value:
            out.add(value.upper())
        elif isinstance(value, (list, tuple)):
            out.update(str(v).upper() for v in value if v)
    return out


def _collect_symbols(data: Any) -> set[str]:
    out: set[str] = set()

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and key.lower() in _SYMBOL_KEYS:
            for match in _TICKER_RE.finditer(node):
                out.add(match.group(1).upper())

    walk(data)
    return out


def _collect_numbers(data: Any) -> list[float]:
    out: list[float] = []

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            out.append(float(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)

    walk(data)
    return out


def _collect_actions(data: Any) -> list[str]:
    out: list[str] = []

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v, key)
        elif isinstance(node, str) and key.lower() in _ACTION_KEYS and node:
            out.append(node.upper())

    walk(data)
    return out


__all__ = ["AdvisoryCollector", "is_compute_tool"]
