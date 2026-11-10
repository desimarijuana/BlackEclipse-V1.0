"""Explainable method suitability.

The score answers one question: *how well does this method fit the stated
problem?* It is not a probability of profit, not a prediction, and not an edge
claim. Every point is printed with the factor that awarded it, and a missing
constraint lowers confidence instead of being silently treated as a match.
"""

from __future__ import annotations

import re
from typing import Any

_OBJECTIVE_SYNONYMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("volatility_forecasting", ("volatility", "variance", "garch", "realized", "vol forecast")),
    ("realized_volatility", ("realized", "intraday variance")),
    ("regime_detection", ("regime", "state", "markov", "change point", "structural break")),
    ("mean_reversion", ("mean reversion", "revert", "ornstein", "half-life", "half life")),
    ("statistical_arbitrage", ("stat arb", "pairs", "cointegration", "relative value")),
    ("spread_modeling", ("spread", "pairs")),
    ("tail_risk", ("tail", "extreme value", "cvar", "expected shortfall", "var")),
    ("value_at_risk", ("value at risk", "var", "risk")),
    ("factor_exposure", ("factor", "capm", "fama", "exposure")),
    ("order_flow", ("order flow", "liquidity", "vpin", "kyle", "imbalance")),
    ("optimal_execution", ("execution", "market impact", "slippage", "almgren")),
    ("momentum", ("momentum", "trend")),
    ("trend_following", ("trend", "momentum")),
    ("directional_prediction", ("predict", "direction", "classification", "machine learning")),
    ("risk_modeling", ("risk", "drawdown", "volatility targeting")),
)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _objective_terms(objective: str) -> set[str]:
    text = _norm(objective)
    terms: set[str] = set()
    for canonical, synonyms in _OBJECTIVE_SYNONYMS:
        if any(syn in text for syn in synonyms):
            terms.add(canonical)
    if not terms and text:
        terms.update(re.findall(r"[a-z]{4,}", text))
    return terms


def _matches(method_objective: str, wanted: set[str]) -> bool:
    if not wanted:
        return False
    norm = _norm(method_objective).replace(" ", "_")
    return any(term in norm or norm in term for term in wanted)


def _input_matches(required: str, available: set[str]) -> bool:
    if not available:
        return False
    req = _norm(required).replace("_", " ")
    return any(req in item or item in req for item in available)


def _horizon(value: Any) -> str:
    text = _norm(value)
    if not text:
        return ""
    if any(token in text for token in ("min", "tick", "hour", "intraday", "15m", "5m", "1m")):
        return "intraday"
    if any(token in text for token in ("week", "1w", "weekly")):
        return "position"
    if any(token in text for token in ("month", "1mo", "monthly", "year", "long")):
        return "long-term"
    if any(token in text for token in ("day", "1d", "daily", "swing")):
        return "swing"
    return text


def score_method(method: dict[str, Any], constraints: dict[str, Any] | None = None) -> dict[str, Any]:
    constraints = constraints or {}
    objective = constraints.get("objective") or constraints.get("problem") or ""
    available = {
        _norm(x).replace("_", " ")
        for x in (constraints.get("availableData") or constraints.get("data") or [])
        if str(x).strip()
    }
    instrument = _norm(constraints.get("instrument") or constraints.get("assetClass")
                       or constraints.get("symbol") or "")
    frequency = _norm(constraints.get("frequency") or constraints.get("timeframe") or "")
    complexity_max = constraints.get("complexityMax")
    wanted = _objective_terms(objective)

    factors: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1. Objective fit — 25 points.
    method_objectives = method.get("objective") or []
    if wanted:
        hits = [o for o in method_objectives if _matches(o, wanted)]
        points = 25 if hits else (8 if not method_objectives else 0)
        reason = (
            f"serves {', '.join(hits)}" if hits else
            "does not state the requested objective"
        )
        factors.append({"name": "objective_fit", "points": points, "max": 25, "reason": reason})
        if not hits:
            warnings.append("the method's stated objective does not match the request")
    else:
        factors.append({"name": "objective_fit", "points": 12, "max": 25,
                        "reason": "no objective was stated; scored neutral"})
        warnings.append("objective not stated — suitability is a weak prior")

    # 2. Data compatibility — 20 points.
    inputs = method.get("inputs") or []
    if inputs and available:
        matched = sum(1 for item in inputs if _input_matches(item.get("name", ""), available))
        points = round(20 * matched / len(inputs))
        factors.append({"name": "data_compatibility", "points": points, "max": 20,
                        "reason": f"{matched}/{len(inputs)} required inputs are supplied"})
        if matched < len(inputs):
            warnings.append("some required inputs are not supplied")
    elif inputs:
        factors.append({"name": "data_compatibility", "points": 10, "max": 20,
                        "reason": "data availability not stated; scored neutral"})
        warnings.append("data availability not stated — verify the required inputs")
    else:
        factors.append({"name": "data_compatibility", "points": 5, "max": 20,
                        "reason": "the method does not declare its inputs"})
        warnings.append("the method specification does not declare inputs")

    # 3. Frequency fit — 5 points.
    frequencies = [_norm(f) for f in method.get("frequencies") or []]
    if frequency and frequencies:
        if any(frequency in f or f in frequency for f in frequencies):
            factors.append({"name": "frequency_fit", "points": 5, "max": 5,
                            "reason": f"supports a {frequency} decision frequency"})
        else:
            factors.append({"name": "frequency_fit", "points": 0, "max": 5,
                            "reason": f"does not declare a {frequency} frequency"})
            warnings.append(f"the method may not support a {frequency} frequency")
    else:
        factors.append({"name": "frequency_fit", "points": 3, "max": 5,
                        "reason": "decision frequency not stated; scored neutral"})

    # 4. Horizon fit — 10 points. The catalog is horizon-wide; a method can
    # support several horizons, and the score names them.
    requested_horizon = _horizon(constraints.get("horizon") or frequency)
    method_horizons = [_horizon(h) for h in method.get("horizons") or []]
    if requested_horizon and method_horizons:
        if requested_horizon in method_horizons:
            factors.append({"name": "horizon_fit", "points": 10, "max": 10,
                            "reason": f"supports the {requested_horizon} horizon"})
        else:
            factors.append({"name": "horizon_fit", "points": 2, "max": 10,
                            "reason": f"does not declare the {requested_horizon} horizon "
                                      f"({', '.join(method_horizons)})"})
            warnings.append(f"the method may not fit a {requested_horizon} horizon")
    else:
        factors.append({"name": "horizon_fit", "points": 5, "max": 10,
                        "reason": "horizon not stated; scored neutral"})

    # 5. Market applicability — 10 points.
    instruments = [_norm(i) for i in method.get("instruments") or []]
    if instrument and instruments:
        if any(instrument in i or i in instrument for i in instruments):
            factors.append({"name": "market_fit", "points": 10, "max": 10,
                            "reason": f"applies to {instrument}"})
        else:
            factors.append({"name": "market_fit", "points": 2, "max": 10,
                            "reason": f"does not primarily target {instrument}"})
            warnings.append(f"not a primary {instrument} method")
    else:
        factors.append({"name": "market_fit", "points": 5, "max": 10,
                        "reason": "market not stated or method not market-specific"})

    # 6. Assumption compatibility — 10 points (declared, not verified).
    assumptions = method.get("assumptions") or []
    factors.append({
        "name": "assumption_transparency", "points": 10 if assumptions else 3, "max": 10,
        "reason": (f"{len(assumptions)} assumptions are declared; each must be tested"
                   if assumptions else "no assumptions are declared"),
    })
    if not assumptions:
        warnings.append("no assumptions declared — a fit score cannot judge them")

    # 7. Research support — 8 points. Evidence level, not citation count alone.
    level = int(method.get("evidenceLevel") or 2)
    factors.append({"name": "research_support", "points": min(8, round(level * 1.6)), "max": 8,
                    "reason": f"catalog evidence level {level}/5"})

    # 8. Reproducibility — 7 points.
    impl = _norm(method.get("implementationStatus") or "none")
    repro = _norm(method.get("reproductionStatus") or "none")
    impl_points = {"tested": 6, "builtin": 5, "implemented": 4, "specified": 2, "none": 0}.get(impl, 0)
    repro_points = {"reproduced": 1, "partial": 1, "attempted": 1}.get(repro, 0)
    factors.append({"name": "reproducibility", "points": min(7, impl_points + repro_points),
                    "max": 7,
                    "reason": f"implementation={impl}, reproduction={repro}"})

    # 9. Computational feasibility — 5 points.
    complexity = int(method.get("complexity") or 3)
    feasible = max(0, 6 - complexity)
    if complexity_max is not None and complexity > int(complexity_max):
        feasible = 0
        warnings.append(f"complexity {complexity} exceeds the requested maximum {complexity_max}")
    factors.append({"name": "computational_feasibility", "points": min(5, feasible), "max": 5,
                    "reason": f"complexity {complexity}/5"})

    score = int(sum(f["points"] for f in factors))
    return {
        "methodId": method.get("methodId") or method.get("id"),
        "name": method.get("name"),
        "score": score,
        "fitPercent": score,
        "factors": factors,
        "warnings": warnings,
        "caveats": [
            "This score is methodological suitability, not a probability of profit.",
            "It does not validate the assumptions on your data; that requires tests.",
            "A higher score is not a recommendation to trade.",
        ],
    }


def compare_methods(methods: list[dict[str, Any]],
                    constraints: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    scored = [score_method(m, constraints) for m in methods]
    scored.sort(key=lambda row: row["score"], reverse=True)
    return scored


__all__ = ["compare_methods", "score_method"]
