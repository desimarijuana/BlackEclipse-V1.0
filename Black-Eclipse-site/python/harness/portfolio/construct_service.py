"""Portfolio construction orchestration (§33, §38).

Extracted from `portfolio/service.py` so the service facade stays within its size
budget. The heavy data-prep / estimation / dispatch / persistence flow lives here;
`PortfolioService.construct` is a thin delegate.

Data acquisition goes through the shared Market Data Gateway (`service.gateway`),
never a provider directly. When no covariance is supplied it is estimated from
gateway history through the deterministic `estimation` layer. Results are
proposal-only and may be persisted as a rebalance plan for audit/reproducibility.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional, Sequence

from .errors import PortfolioError
from .models import new_id, now_iso as _now_iso
from .money import D

ENGINE_VERSION = "portfolio-engine/1.1.0"


def _data_version(symbols: Sequence[str], covariance: Any, method: str) -> str:
    """A stable content hash of the exact optimization inputs (reproducibility)."""
    blob = json.dumps(
        {"symbols": list(symbols), "method": method, "covariance": covariance},
        default=str, sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


async def construct_payload(service: Any, payload: dict[str, Any], *,
                            actor_id: Optional[str] = None) -> dict[str, Any]:
    from . import construction as _construction
    from .estimation import (align_returns, estimate_covariance,
                             estimate_expected_returns, estimate_factor_loadings)

    symbols = list(payload.get("symbols") or [])
    method = payload.get("method") or "min_variance"
    portfolio_id = payload.get("portfolio_id")
    portfolio = None
    if portfolio_id:
        try:
            portfolio = service._require_portfolio(portfolio_id, actor_id)
        except PortfolioError as exc:
            payload_out = exc.to_dict()
            return {"available": False, "status": "FAILED", "error": payload_out,
                    "reason": payload_out.get("message", "portfolio not accessible")}
    if not symbols and portfolio_id:
        rows = service.store.list_materialized_positions(portfolio_id)
        symbols = [s for s, r in rows.items() if D(r["quantity"]) != 0]
    if not symbols:
        return {"available": False, "status": "SOLVER_ERROR",
                "reason": "no symbols supplied and no open positions to derive them from"}

    covariance = payload.get("covariance")
    expected_returns = payload.get("expected_returns") or payload.get("expectedReturns")
    diagnostics: dict[str, Any] = {}
    returns = payload.get("returns")
    if covariance is None or (method in ("mean_variance", "factor_constrained", "black_litterman")
                              and expected_returns is None):
        if returns is None and service.gateway:
            closes = await service._fetch_histories(symbols, service.gateway)
            series = {s: [{"date": str(i), "close": c} for i, c in enumerate(closes[s])]
                      for s in closes}
            aligned = align_returns(series)
            if aligned.get("available"):
                returns = aligned["returns"]
                diagnostics["alignment"] = {
                    "commonDates": aligned["commonDates"],
                    "observations": aligned["observations"],
                    "excluded": aligned["excluded"],
                }
            else:
                diagnostics["alignment"] = {"available": False, "reason": aligned.get("reason")}
        if returns:
            if covariance is None:
                cov = estimate_covariance(
                    returns, method=payload.get("covariance_method", "sample"),
                    shrinkage=payload.get("shrinkage"),
                    annualize=bool(payload.get("annualize", False)))
                diagnostics["covariance"] = {"method": cov.get("method"),
                                             "diagnostics": cov.get("diagnostics"),
                                             "warnings": cov.get("warnings")}
                covariance = cov.get("covariance")
            if expected_returns is None and method in ("mean_variance", "factor_constrained"):
                er = estimate_expected_returns(
                    returns, method=payload.get("expected_returns_method", "arithmetic"))
                if er.get("available"):
                    expected_returns = [er["expectedReturns"][s] for s in symbols]
                    diagnostics["expectedReturns"] = er.get("meta")
    if not covariance:
        return {"available": False, "status": "SOLVER_ERROR",
                "reason": "no covariance supplied and none could be estimated",
                "diagnostics": diagnostics}

    factor_loadings = payload.get("factor_loadings")
    if method == "factor_constrained" and not factor_loadings and payload.get("factor_returns") \
            and returns:
        est = estimate_factor_loadings(returns, payload["factor_returns"])
        if est.get("available"):
            factor_loadings = est["loadings"]
            diagnostics["factorLoadings"] = {"factors": est["factors"], "r2": est.get("r2"),
                                             "observations": est["observations"]}

    result = _construction.construct(
        symbols=symbols, method=method, covariance=covariance,
        constraints_payload=payload.get("constraints") or payload,
        expected_returns=expected_returns,
        benchmark_weights=payload.get("benchmark_weights"),
        market_weights=payload.get("market_weights"),
        risk_budgets=payload.get("risk_budgets"),
        risk_aversion=float(payload.get("risk_aversion") or 1.0),
        target_volatility=(float(payload["target_volatility"])
                           if payload.get("target_volatility") is not None else None),
        tau=float(payload.get("tau") or 0.05),
        views=payload.get("views"),
        factor_loadings=factor_loadings,
        factor_constraints=payload.get("factor_constraints"),
    )
    result["diagnostics"] = {**diagnostics, **(result.get("diagnostics") or {})}
    if portfolio is not None:
        result["portfolioId"] = portfolio["id"]
    result.setdefault("execution", "proposal-only: no trades are placed; requires user approval")

    # Immutable run record: persist the exact inputs, constraints, status and
    # independently-validated target so any later result is reproducible from
    # versioned inputs even after market data changes.
    run_id = new_id("run")
    result["runId"] = run_id
    result["engineVersion"] = ENGINE_VERSION
    result["dataVersion"] = _data_version(symbols, covariance, method)
    if payload.get("persist", True):
        try:
            service.store.save_construction_run(
                run_id, portfolio["id"] if portfolio else None,
                method=result.get("method") or method, status=str(result.get("status")),
                symbols=symbols, target=result.get("weights") or {},
                constraints=payload.get("constraints") or {
                    k: payload[k] for k in (
                        "min_weights", "max_weights", "groups", "group_caps", "group_membership",
                        "factor_constraints", "turnover_cap", "current_weights", "long_only")
                    if k in payload
                },
                validation=result.get("validation"), payload=result,
                data_version=result["dataVersion"], engine_version=ENGINE_VERSION,
                created_by=actor_id,
            )
        except Exception:  # noqa: BLE001 - persistence failure must not lose the result
            result["diagnostics"]["runPersisted"] = False

    if result.get("available") and result.get("weights") and portfolio is not None \
            and payload.get("persist", True):
        plan_id = new_id("plan")
        recs = [{
            "id": new_id("rec"), "symbol": symbol, "action": "TARGET", "quantity": None,
            "price": None, "estimatedValue": None, "estFees": None, "taxImpact": None,
            "estRealizedPnl": None,
            "reason": f"{result.get('method')} target weight {round(weight * 100, 4)}%",
        } for symbol, weight in result["weights"].items()]
        service.store.save_rebalance_plan(
            plan_id, portfolio["id"], as_of=_now_iso(),
            method=f"construct:{result.get('method')}", status="PROPOSED",
            target=result["weights"], payload=result, recommendations=recs, created_by=actor_id,
        )
        result["planId"] = plan_id
    return result


__all__ = ["construct_payload"]
