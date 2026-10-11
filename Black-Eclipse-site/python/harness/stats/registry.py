"""Registry of the fourteen statistical tools.

A single lookup maps a stable tool name to its spec (description, JSON input
schema, and deterministic `run`). `run_tool` raises `StatsError` for the HTTP
layer to map; `run_tool_safe` returns an error envelope for agent tools, so a
failure is always a structured, non-fabricated response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from . import (
    m_autocorrelation,
    m_beta,
    m_cointegration,
    m_correlation,
    m_drawdown,
    m_features,
    m_information,
    m_leadlag,
    m_outliers,
    m_regime,
    m_regression,
    m_returns,
    m_stationarity,
    m_volatility,
)
from .base import INVALID_INPUT, StatsError, make_response


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[[dict[str, Any]], dict[str, Any]]
    category: str


_MODULES = [
    ("calculate_returns", "returns", m_returns),
    ("calculate_volatility", "volatility", m_volatility),
    ("calculate_correlation", "relationships", m_correlation),
    ("calculate_beta", "relationships", m_beta),
    ("calculate_drawdown", "risk", m_drawdown),
    ("calculate_stationarity", "inference", m_stationarity),
    ("calculate_cointegration", "inference", m_cointegration),
    ("calculate_autocorrelation", "inference", m_autocorrelation),
    ("calculate_regression", "regression", m_regression),
    ("calculate_regime", "regime", m_regime),
    ("build_features", "features", m_features),
    ("detect_outliers", "anomaly", m_outliers),
    ("analyze_lead_lag", "relationships", m_leadlag),
    ("calculate_information_coefficient", "factor", m_information),
]

TOOLS: dict[str, ToolSpec] = {
    name: ToolSpec(name=name, description=mod.DESCRIPTION, input_schema=mod.INPUT_SCHEMA,
                   run=mod.run, category=category)
    for name, category, mod in _MODULES
}

TOOL_NAMES: tuple[str, ...] = tuple(TOOLS.keys())


def get_tool(name: str) -> ToolSpec:
    spec = TOOLS.get(name)
    if spec is None:
        raise StatsError(INVALID_INPUT, f"unknown statistical tool: {name}", 404)
    return spec


def register(name: str, category: str, mod: Any) -> None:
    TOOLS[name] = ToolSpec(name=name, description=mod.DESCRIPTION,
                           input_schema=mod.INPUT_SCHEMA, run=mod.run, category=category)


def run_tool(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_tool(name).run(args or {})


def run_tool_safe(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Agent-facing dispatch: never raises; failures become error envelopes."""
    try:
        return run_tool(name, args)
    except StatsError as exc:
        return make_response(name, args or {}, status="error",
                             errors=[exc.to_dict()], warnings=[exc.message])
    except Exception as exc:  # noqa: BLE001 - last-resort, always structured
        return make_response(name, args or {}, status="error",
                             errors=[{"code": "INTERNAL_ERROR", "message": str(exc)}])


def catalog() -> list[dict[str, Any]]:
    return [{"name": s.name, "description": s.description, "category": s.category,
             "inputSchema": s.input_schema} for s in TOOLS.values()]


__all__ = ["ToolSpec", "TOOLS", "TOOL_NAMES", "get_tool", "register", "run_tool", "run_tool_safe", "catalog"]
