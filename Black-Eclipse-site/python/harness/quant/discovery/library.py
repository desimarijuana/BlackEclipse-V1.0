"""Method library — cards and fit-ranked recommendations.

The recommendation engine is deterministic and explainable: every score is a sum
of the factors printed with it. It is a *starting point*, not a claim that the
method has an edge on the user's data. The next step is always the same: turn it
into a spec, test it, and let the evidence decide.
"""

from __future__ import annotations

from typing import Any, Optional

from .taxonomy import FAMILIES, MethodFamily, family_by_id

_HORIZON_ALIASES = {
    "intraday": {"intraday", "scalping", "day"},
    "swing": {"swing", "days", "short-term", "short"},
    "position": {"position", "weeks", "medium-term", "medium"},
    "long-term": {"long-term", "months", "investing", "long"},
}

_ASSET_ALIASES = {
    "equities": {"equities", "equity", "stocks", "stock", "shares"},
    "equity index": {"equities", "equity", "index", "etf", "spy", "qqq"},
    "single stocks": {"equities", "single stocks", "stocks"},
    "fx": {"fx", "forex", "currencies", "currency"},
    "crypto": {"crypto", "bitcoin", "btc", "ethereum", "eth"},
    "futures": {"futures", "commodities", "commodity"},
    "commodity futures": {"futures", "commodities", "commodity"},
    "etfs": {"etfs", "equities", "index"},
    "crypto perpetuals": {"crypto", "perpetuals", "perp"},
}

_OBJECTIVE_FAMILIES = {
    "income": {"options_income", "carry_futures", "crypto_funding_basis"},
    "growth": {"trend_ema_cross", "trend_donchian_breakout", "momentum_cross_sectional",
               "volatility_breakout"},
    "preservation": {"low_volatility", "trend_ema_cross", "mean_reversion_bollinger"},
    "diversification": {"carry_futures", "trend_ema_cross", "low_volatility",
                        "pairs_cointegration"},
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", " ")


def _asset_matches(family: MethodFamily, asset_class: str) -> bool:
    wanted = {_norm(asset_class)}
    for instrument in family.instruments:
        key = _norm(instrument)
        aliases = _ASSET_ALIASES.get(instrument, set()) | _ASSET_ALIASES.get(key, set())
        if wanted & (aliases | {key}):
            return True
    return False


def _horizon_matches(family: MethodFamily, horizon: str) -> bool:
    h = _norm(horizon)
    if not h:
        return True
    for item in family.horizons:
        aliases = _HORIZON_ALIASES.get(_norm(item), {_norm(item)})
        if h in aliases or any(h in a or a in h for a in aliases):
            return True
    return False


def list_method_families(*, category: Optional[str] = None,
                         asset_class: Optional[str] = None,
                         horizon: Optional[str] = None,
                         max_complexity: Optional[int] = None) -> list[dict[str, Any]]:
    out = []
    for family in FAMILIES:
        if category and _norm(category) != _norm(family.category):
            continue
        if asset_class and not _asset_matches(family, asset_class):
            continue
        if horizon and not _horizon_matches(family, horizon):
            continue
        if max_complexity is not None and family.complexity > max_complexity:
            continue
        out.append(family.to_dict())
    return out


def get_method_card(method_id: str, *, symbol: Optional[str] = None,
                    interval: str = "1d") -> dict[str, Any]:
    family = family_by_id(method_id)
    if family is None:
        from ..errors import QuantError
        raise QuantError(f"unknown method family {method_id!r}",
                         detail={"methods": [f.id for f in FAMILIES]})
    card = family.to_dict()
    card["playbook"] = {
        "understand": family.thesis,
        "why_it_might_work": family.edge_source,
        "how_to_express_it": list(family.signals),
        "where_it_fails": list(family.failure_modes),
        "how_to_validate": family.validation,
        "capacity": family.capacity,
    }
    if family.builder and symbol:
        try:
            from .synthesize import build_strategy  # noqa: PLC0415
            card["exampleSpec"] = build_strategy(
                method_id, symbol=symbol, interval=interval
            )
        except Exception as exc:  # noqa: BLE001
            card["exampleSpecError"] = str(exc)
    card["nextStep"] = (
        "Register a hypothesis, synthesize the spec, then run the research suite. "
        "A method card is a prior, not evidence."
    )
    return card


def recommend_methods(profile: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    """Rank method families for a user's constraints.

    `profile` accepts: assetClass, horizon, riskTolerance (low|medium|high),
    objective (income|growth|preservation|diversification), capital,
    availableData (list of strings), allowShort (bool), complexityMax (int),
    regime (e.g. "trending up", "flat"), symbol, interval.
    """
    asset = profile.get("assetClass") or profile.get("asset") or ""
    horizon = profile.get("horizon") or ""
    objective = _norm(profile.get("objective"))
    risk = _norm(profile.get("riskTolerance") or "medium")
    available = {_norm(x) for x in (profile.get("availableData") or [])}
    allow_short = bool(profile.get("allowShort", True))
    complexity_max = profile.get("complexityMax")
    regime = _norm(profile.get("regime"))
    symbol = profile.get("symbol")
    interval = profile.get("interval") or "1d"

    ranked: list[dict[str, Any]] = []
    for family in FAMILIES:
        score = 0.0
        reasons: list[str] = []
        warnings: list[str] = []

        if asset and _asset_matches(family, asset):
            score += 4
            reasons.append(f"trades {asset}")
        elif asset:
            warnings.append(f"not primarily a {asset} method")

        if horizon and _horizon_matches(family, horizon):
            score += 2
            reasons.append(f"fits a {horizon} horizon")
        elif horizon:
            warnings.append(f"less natural for a {horizon} horizon")

        if objective:
            if family.id in _OBJECTIVE_FAMILIES.get(objective, set()):
                score += 2
                reasons.append(f"matches the {objective} objective")
            else:
                warnings.append(f"not a typical {objective} method")

        if risk == "low":
            if family.category in ("carry", "low_volatility", "options_income"):
                score += 1.5
                reasons.append("lower-risk family")
            elif family.category in ("trend", "momentum", "stat_arb"):
                warnings.append("can experience sharp drawdowns")
        elif risk == "high":
            if family.category in ("trend", "momentum", "volatility"):
                score += 1
                reasons.append("can express a high-risk/high-reward view")

        if available:
            missing = [req for req in family.data_requirements
                       if _norm(req) not in available
                       and not any(_norm(req) in a or a in _norm(req) for a in available)]
            if missing:
                score -= 2 * len(missing)
                warnings.append("needs data you have not listed: " + ", ".join(missing))
            else:
                score += 1.5
                reasons.append("all stated data requirements are available")

        if family.requires and not allow_short:
            if any("short" in req for req in family.requires):
                score -= 4
                warnings.append("requires shorting, which is disabled")

        if complexity_max is not None:
            if family.complexity <= int(complexity_max):
                score += 0.5
            else:
                score -= 2
                warnings.append(f"complexity {family.complexity} exceeds your limit")

        if regime:
            if any(regime == _norm(r) or regime in _norm(r) for r in family.best_regimes):
                score += 1.5
                reasons.append(f"prior says it fits a {regime} regime")
            if any(regime == _norm(r) or regime in _norm(r) for r in family.worst_regimes):
                score -= 1.5
                warnings.append(f"prior says it struggles in a {regime} regime")

        score += family.evidence * 0.4
        ranked.append({
            "methodId": family.id,
            "name": family.name,
            "category": family.category,
            "fitScore": round(score, 4),
            "fitPercent": round(max(0.0, min(100.0, (score + 6.0) / 22.0 * 100.0)), 1),
            "reasons": reasons,
            "warnings": warnings,
            "complexity": family.complexity,
            "evidence": family.evidence,
            "turnover": family.turnover,
            "requires": list(family.requires),
        })

    ranked.sort(key=lambda row: (-row["fitScore"], row["methodId"]))
    top = ranked[: max(1, min(int(limit), len(ranked)))]
    out = {
        "profile": profile,
        "recommendations": top,
        "note": "fit ranks the METHOD to your constraints; it says nothing about "
                "whether the method has an edge on your data. Test it.",
    }
    if symbol and top:
        try:
            from .synthesize import build_strategy  # noqa: PLC0415
            out["starterSpec"] = build_strategy(
                top[0]["methodId"], symbol=symbol, interval=interval
            )
        except Exception:  # noqa: BLE001
            pass
    return out


__all__ = ["get_method_card", "list_method_families", "recommend_methods"]
