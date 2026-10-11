"""Orchestration facade for the Factor & Alpha Research Lab.

Thin glue between the pure engine (`factors.engine`), the safe formula language
(`stats.formula`) and the registry/persistence (`factors.store`). Everything
deterministic is delegated to the engine; nothing here re-implements math.
"""

from __future__ import annotations

import math
import re
from typing import Any, Optional

import numpy as np

from ..stats.base import INVALID_INPUT, StatsError
from ..stats.formula import FormulaError, evaluate as eval_formula, parse as parse_formula
from . import engine as E
from .library import get_builtin, list_builtins
from .models import FactorDefinition
from .store import FactorStore, build_version_string

_store: Optional[FactorStore] = None


def set_factor_store(store: Optional[FactorStore]) -> None:
    global _store
    _store = store


def get_factor_store() -> Optional[FactorStore]:
    return _store


def _require_store() -> FactorStore:
    if _store is None:
        raise StatsError("UNAVAILABLE", "the factor store is unavailable", 503)
    return _store


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "factor"
    return base


def _finite_or_none(value: Any) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ── expression validation / preview ──────────────────────────────────────────

def validate_expression(expression: str, *, sample: Optional[dict[str, list[float]]] = None) -> dict[str, Any]:
    """Static + (optionally) dynamic validation of a factor formula."""
    errors: list[dict[str, Any]] = []
    variables: list[str] = []
    functions: list[str] = []
    if not expression or not expression.strip():
        return {"status": "invalid", "valid": False, "variables": [], "functions": [],
                "errors": [{"code": "EMPTY", "message": "expression is empty"}]}
    try:
        parsed = parse_formula(expression)
        variables = list(parsed.variables)
        functions = list(parsed.functions)
    except FormulaError as exc:
        return {"status": "invalid", "valid": False, "variables": [], "functions": [],
                "errors": [{"code": getattr(exc, "code", "SYNTAX"), "message": str(exc)}]}

    coverage = None
    preview: list[Optional[float]] = []
    if sample:
        missing = [v for v in variables if v not in sample]
        if missing:
            errors.append({"code": "MISSING_INPUT", "message": f"missing sample inputs: {missing}"})
        else:
            try:
                result, _ = eval_formula(expression, {k: np.asarray(v, dtype=float) for k, v in sample.items()})
                arr = np.asarray(result, dtype=float).ravel()
                finite = int(np.isfinite(arr).sum())
                coverage = finite / arr.size if arr.size else 0.0
                preview = [None if not math.isfinite(float(x)) else float(x) for x in arr[-50:]]
            except FormulaError as exc:
                errors.append({"code": getattr(exc, "code", "RUNTIME"), "message": str(exc)})

    valid = not errors
    return {
        "status": "valid" if valid else "invalid", "valid": valid, "variables": variables,
        "functions": functions, "coverage": coverage, "preview": preview, "errors": errors,
    }


# ── factor registry operations ───────────────────────────────────────────────

def save_factor(defn: FactorDefinition, *, bump: str = "minor", changelog: Optional[str] = None,
                built_in: bool = False) -> dict[str, Any]:
    store = _require_store()
    existing = store.get_factor_by_name(defn.name) if defn.factor_id is None else store.get_factor(defn.factor_id)
    factor_id = existing["id"] if existing else (defn.factor_id or f"fac_{_slug(defn.name)}")
    prev_version = existing["latestVersion"] if existing else None
    version = "1.0.0" if prev_version is None else build_version_string(prev_version, bump)

    validation = validate_expression(defn.expression)
    inputs = list(defn.inputs) or list(validation["variables"])
    # Version the factor even if the expression fails static validation; the
    # record carries its validation status so nothing is silently "valid".
    store.upsert_factor(
        factor_id=factor_id, name=defn.name, description=defn.description, family=defn.family,
        owner=defn.owner, direction=defn.direction, frequency=defn.frequency,
        asset_class=defn.asset_class, tags=defn.tags, latest_version=version, built_in=built_in,
    )
    ver = store.add_version(
        factor_id=factor_id, version=version, expression=defn.expression, inputs=inputs,
        params=defn.parameters, normalization=defn.normalization, missing_policy=defn.missing_policy,
        lookback=defn.lookback, output_type=defn.output_type, pit_safe=defn.pit_safe, changelog=changelog,
    )
    store.set_validation(factor_id, "valid" if validation["valid"] else "invalid")
    if existing is None:
        store.add_lineage(child_type="factor", child_id=factor_id, parent_type="library",
                          parent_id=defn.family, relation="family")
    return {"factor": store.get_factor(factor_id), "version": ver, "validation": validation}


def list_factors(*, family: Optional[str] = None) -> list[dict[str, Any]]:
    return _require_store().list_factors(family=family)


def get_factor(factor_id: str, *, include_versions: bool = False) -> Optional[dict[str, Any]]:
    store = _require_store()
    factor = store.get_factor(factor_id)
    if factor is None:
        return None
    if include_versions:
        factor = dict(factor)
        factor["versions"] = store.list_versions(factor_id)
    return factor


def get_factor_version(factor_id: str, version: Optional[str] = None) -> Optional[dict[str, Any]]:
    store = _require_store()
    if version is None:
        factor = store.get_factor(factor_id)
        if factor is None:
            return None
        version = factor["latestVersion"]
    return store.get_version(factor_id, version)


# ── panel construction ───────────────────────────────────────────────────────

def build_factor_panel(expression: str, series_by_symbol: dict[str, dict[str, list[float]]],
                       symbols: list[str]) -> tuple[np.ndarray, list[str]]:
    """Evaluate the formula per instrument and stack into a (T, N) panel."""
    warnings: list[str] = []
    columns: list[np.ndarray] = []
    length: Optional[int] = None
    for sym in symbols:
        ctx = series_by_symbol.get(sym) or {}
        if not ctx:
            warnings.append(f"{sym}: no series supplied")
            columns.append(np.array([np.nan]))
            continue
        try:
            result, _ = eval_formula(expression, {k: np.asarray(v, dtype=float) for k, v in ctx.items()})
            arr = np.asarray(result, dtype=float).ravel()
        except FormulaError as exc:
            warnings.append(f"{sym}: {exc}")
            arr = np.array([np.nan])
        if length is None:
            length = arr.size
        elif arr.size != length:
            arr = np.resize(arr, length)
        columns.append(arr)
    if not columns:
        return np.empty((0, 0)), warnings
    T = min(c.size for c in columns)
    panel = np.column_stack([c[:T] for c in columns])
    return panel, warnings


def series_panel(series_by_symbol: dict[str, dict[str, list[float]]], symbols: list[str],
                 field: str) -> np.ndarray:
    cols = []
    for sym in symbols:
        ctx = series_by_symbol.get(sym) or {}
        arr = np.asarray(ctx.get(field, []), dtype=float)
        cols.append(arr)
    T = min((c.size for c in cols), default=0)
    if T == 0:
        return np.empty((0, 0))
    return np.column_stack([c[:T] for c in cols])


# ── evaluation ───────────────────────────────────────────────────────────────

def evaluate(
    expression: str, series_by_symbol: dict[str, dict[str, list[float]]], symbols: list[str],
    *, horizons: list[int], method: str = "pearson", min_obs: int = 5,
    periods_per_year: Optional[int] = None, expected_direction: Optional[str] = None,
    membership: Optional[Any] = None,
) -> dict[str, Any]:
    """Compute IC, Rank IC and decay for a factor against forward returns.

    ``membership`` is an optional ``(T, N)`` bool mask from
    `factors.universe.membership_mask`; non-member cells are excluded so a factor
    is never evaluated over names that were not in the universe on that date.
    """
    factor_panel, warnings = build_factor_panel(expression, series_by_symbol, symbols)
    prices = series_panel(series_by_symbol, symbols, "close")
    T = min(factor_panel.shape[0] if factor_panel.size else 0, prices.shape[0])
    factor_panel = factor_panel[:T]
    prices = prices[:T]
    universe_coverage = 1.0
    if membership is not None:
        from .universe import apply_membership  # noqa: PLC0415

        m = np.asarray(membership, dtype=bool)[:T]
        universe_coverage = float(m.mean()) if m.size else 0.0
        factor_panel = apply_membership(factor_panel, m)
    if T < min_obs + max(horizons, default=1):
        raise StatsError("INSUFFICIENT_DATA", "not enough observations for the requested horizons", 422)

    h0 = int(min(horizons))
    fwd0 = E.forward_returns(prices, h0)
    ic, counts = E.cross_sectional_ic(factor_panel, fwd0, method=method, min_obs=min_obs)
    rank_ic, rank_counts = E.cross_sectional_ic(factor_panel, fwd0, method="spearman", min_obs=min_obs)
    decay = E.factor_decay(factor_panel, prices, horizons, method=method, min_obs=min_obs,
                           periods_per_year=periods_per_year)

    ic_stats = E.ic_summary(ic, counts, periods_per_year=periods_per_year)
    rank_stats = E.ic_summary(rank_ic, rank_counts, periods_per_year=periods_per_year)

    coverage = float(np.isfinite(factor_panel).mean()) if factor_panel.size else 0.0
    return {
        "horizons": list(horizons), "method": method, "minObs": min_obs,
        "expectedDirection": expected_direction,
        "ic": {
            "series": E._list(ic),  # noqa: SLF001 - intentional: shared JSON coercion
            "counts": [int(c) for c in counts],
            "summary": ic_stats,
        },
        "rankIC": {
            "series": E._list(rank_ic),  # noqa: SLF001
            "counts": [int(c) for c in rank_counts],
            "summary": rank_stats,
        },
        "decay": decay,
        "coverage": coverage,
        "universeCoverage": universe_coverage,
        "observations": int(T),
        "warnings": warnings,
    }


def quantile_portfolio(
    expression: str, series_by_symbol: dict[str, dict[str, list[float]]], symbols: list[str],
    *, quantiles: int = 5, weighting: str = "equal", long_short: bool = True, rebalance: int = 1,
    cost_bps: float = 0.0, min_obs: int = 5, periods_per_year: int = 252, risk_free: float = 0.0,
    membership: Optional[Any] = None,
) -> dict[str, Any]:
    factor_panel, warnings = build_factor_panel(expression, series_by_symbol, symbols)
    prices = series_panel(series_by_symbol, symbols, "close")
    T = min(factor_panel.shape[0] if factor_panel.size else 0, prices.shape[0])
    factor_panel = factor_panel[:T]
    prices = prices[:T]
    if membership is not None:
        from .universe import apply_membership  # noqa: PLC0415

        factor_panel = apply_membership(factor_panel, np.asarray(membership, dtype=bool)[:T])
    returns = prices.copy()
    with np.errstate(divide="ignore", invalid="ignore"):
        fwd = np.full_like(prices, np.nan)
        fwd[:-1] = prices[1:] / prices[:-1] - 1.0
    result = E.quantile_portfolio(
        factor_panel, fwd, quantiles=quantiles, weighting=weighting, long_short=long_short,
        rebalance=rebalance, cost_bps=cost_bps, min_obs=min_obs, periods_per_year=periods_per_year,
        risk_free=risk_free,
    )
    result["warnings"] = warnings
    result["symbols"] = symbols
    return result


def compose(
    panels: list[Any], *, method: str = "equal_zscore", weights: Optional[list[float]] = None,
    forward: Optional[Any] = None, training_rows: Optional[int] = None,
) -> dict[str, Any]:
    combo = E.combine_factors(panels, method=method, weights=weights, forward=forward,
                              training_rows=training_rows)
    composite = combo.pop("composite")
    combo["compositeShape"] = list(np.asarray(composite).shape)
    if forward is not None:
        ic, counts = E.cross_sectional_ic(composite, np.asarray(forward), min_obs=3)
        combo["compositeIC"] = E.ic_summary(ic, counts)
    return combo


def analyze_redundancy(panels: list[Any], *, threshold: float = 0.9) -> dict[str, Any]:
    return E.detect_redundancy(panels, threshold=threshold)


# ── built-in library ─────────────────────────────────────────────────────────

def list_library(*, available_only: bool = False) -> list[dict[str, Any]]:
    return list_builtins(available_only=available_only)


def install_builtins() -> list[dict[str, Any]]:
    """Register the evaluable built-in factors into the registry (idempotent)."""
    store = _require_store()
    created = []
    for spec in list_builtins(available_only=True):
        existing = store.get_factor_by_name(spec["name"])
        if existing:
            continue
        defn = FactorDefinition(
            name=spec["name"], description=spec.get("description", ""), family=spec["family"],
            direction=spec.get("direction"), frequency="1d", asset_class="equity",
            expression=spec["expression"], inputs=list(spec.get("inputs", [])),
            lookback=int(spec.get("lookback", 1)), owner="system", pit_safe=True,
        )
        created.append(save_factor(defn, bump="minor", changelog="built-in library", built_in=True))
    return created


def get_builtin_spec(name: str) -> Optional[dict[str, Any]]:
    return get_builtin(name)


def _mm():
    from ..quant import multiple_testing  # noqa: PLC0415

    return multiple_testing


def deflated_sharpe_for(returns: list[float], *, trial_sharpes: Optional[list[float]] = None,
                        trial_count: Optional[int] = None,
                        sr_variance: Optional[float] = None) -> dict[str, Any]:
    """Deflated Sharpe Ratio (reuses the quant engine — no second implementation)."""
    return _mm().deflated_sharpe(returns, trial_sharpes=trial_sharpes, trial_count=trial_count,
                                 sr_variance=sr_variance)


def overfitting_pbo(candidate_returns: list[list[float]], *, n_splits: int = 16) -> dict[str, Any]:
    """Probability of Backtest Overfitting via CSCV (reuses the quant engine)."""
    return _mm().pbo_cscv(candidate_returns, n_splits=n_splits)


__all__ = [
    "set_factor_store", "get_factor_store", "validate_expression", "save_factor", "list_factors",
    "get_factor", "get_factor_version", "build_factor_panel", "series_panel", "evaluate",
    "quantile_portfolio", "compose", "analyze_redundancy", "list_library", "install_builtins",
    "get_builtin_spec", "deflated_sharpe_for", "overfitting_pbo",
]
