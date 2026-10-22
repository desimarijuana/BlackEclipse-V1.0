"""Macro series identity (A8).

A macro series is an identity, not a string: "POLICY_RATE" is ambiguous
(US fed funds target? the reverse-repo ceiling? the ECB deposit rate?), and two
measures of "the policy rate" must not collide as one series. A generic measure
must never default to a US backend.

This mirrors the TS registry in `src/lib/harness/macro-identity.ts`; the TS side
owns the provider routing (it holds the source registry), while this module lets
the Python layer reason about series identity and reject ambiguity before any
source is attempted.
"""

from __future__ import annotations

from typing import Any, Optional

# Canonical series identities. geography + institution + measure + adjustment +
# frequency; `sourceId` names the TS source family that serves it.
_SERIES: list[dict[str, Any]] = [
    {"id": "US:FRED:FEDFUNDS", "geography": "US", "institution": "FRED", "measure": "fed_funds_effective", "adjustment": "nsa", "frequency": "monthly", "sourceId": "fred-analytics", "providerSeries": "FEDFUNDS"},
    {"id": "US:FRED:DFEDTARU", "geography": "US", "institution": "FRED", "measure": "fed_funds_target_upper", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DFEDTARU"},
    {"id": "US:FRED:DFEDTARL", "geography": "US", "institution": "FRED", "measure": "fed_funds_target_lower", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DFEDTARL"},
    {"id": "US:FRED:RRPONTSYD", "geography": "US", "institution": "FRED", "measure": "reverse_repo_ceiling", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "RRPONTSYD"},
    {"id": "US:FRED:CPIAUCSL", "geography": "US", "institution": "FRED", "measure": "cpi_headline", "adjustment": "sa", "frequency": "monthly", "sourceId": "fred-analytics", "providerSeries": "CPIAUCSL"},
    {"id": "US:FRED:CPILFESL", "geography": "US", "institution": "FRED", "measure": "cpi_core", "adjustment": "sa", "frequency": "monthly", "sourceId": "fred-analytics", "providerSeries": "CPILFESL"},
    {"id": "US:FRED:UNRATE", "geography": "US", "institution": "FRED", "measure": "unemployment_rate", "adjustment": "sa", "frequency": "monthly", "sourceId": "fred-analytics", "providerSeries": "UNRATE"},
    {"id": "US:FRED:GDP", "geography": "US", "institution": "FRED", "measure": "gdp_nominal", "adjustment": "sa", "frequency": "quarterly", "sourceId": "fred-analytics", "providerSeries": "GDP"},
    # The RATES and the DOLLAR an asset analysis needs: a real-yield series is
    # the difference between "gold is expensive" and "gold is expensive
    # because real yields are". The broad dollar index and the volatility index
    # are the other two legs of every gold/growth-factor model.
    {"id": "US:FRED:DFII10", "geography": "US", "institution": "FRED", "measure": "real_yield_10y", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DFII10"},
    {"id": "US:FRED:DFII5", "geography": "US", "institution": "FRED", "measure": "real_yield_5y", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DFII5"},
    {"id": "US:FRED:DGS10", "geography": "US", "institution": "FRED", "measure": "nominal_yield_10y", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DGS10"},
    {"id": "US:FRED:DGS2", "geography": "US", "institution": "FRED", "measure": "nominal_yield_2y", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DGS2"},
    {"id": "US:FRED:T10YIE", "geography": "US", "institution": "FRED", "measure": "breakeven_inflation_10y", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "T10YIE"},
    {"id": "US:FRED:DTWEXBGS", "geography": "US", "institution": "FRED", "measure": "broad_dollar_index", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "DTWEXBGS"},
    {"id": "US:FRED:VIXCLS", "geography": "US", "institution": "FRED", "measure": "equity_volatility_index", "adjustment": "nsa", "frequency": "daily", "sourceId": "fred-analytics", "providerSeries": "VIXCLS"},
    {"id": "EA:ECB:DEPOSIT", "geography": "EA", "institution": "ECB", "measure": "ecb_deposit_facility_rate", "adjustment": "nsa", "frequency": "daily", "sourceId": "ecb", "providerSeries": "deposit"},
    {"id": "EA:ECB:MRR", "geography": "EA", "institution": "ECB", "measure": "ecb_main_refinancing_rate", "adjustment": "nsa", "frequency": "daily", "sourceId": "ecb", "providerSeries": "mrr"},
    {"id": "WLD:WORLDBANK:GDP", "geography": "WLD", "institution": "WorldBank", "measure": "gdp_nominal", "adjustment": "nsa", "frequency": "annual", "sourceId": "worldbank", "providerSeries": "NY.GDP.MKTP.CD"},
]

_GENERIC_MEASURE_FAMILIES = {
    "policy_rate": ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
    "policyrate": ["fed_funds_target_upper", "fed_funds_target_lower", "fed_funds_effective", "reverse_repo_ceiling"],
    "interest_rate": ["fed_funds_effective", "fed_funds_target_upper"],
    "inflation": ["cpi_headline"],
    "cpi": ["cpi_headline"],
    "core_inflation": ["cpi_core"],
    "unemployment": ["unemployment_rate"],
    "gdp": ["gdp_nominal"],
    "real_yield": ["real_yield_10y", "real_yield_5y"],
    "real_rates": ["real_yield_10y", "real_yield_5y"],
    "nominal_yield": ["nominal_yield_10y", "nominal_yield_2y"],
    "treasury_yield": ["nominal_yield_10y", "nominal_yield_2y"],
    "breakeven": ["breakeven_inflation_10y"],
    "breakeven_inflation": ["breakeven_inflation_10y"],
    "dollar_index": ["broad_dollar_index"],
    "broad_dollar": ["broad_dollar_index"],
    "dxy": ["broad_dollar_index"],
    "vix": ["equity_volatility_index"],
    "volatility_index": ["equity_volatility_index"],
}

# Country alias → geography (accepts country names, ISO2, and venue codes).
_GEO_ALIASES = {
    "us": "US", "usa": "US", "united states": "US",
    "ea": "EA", "euro area": "EA", "eurozone": "EA", "eu": "EA",
    "gb": "GB", "uk": "GB", "united kingdom": "GB",
    "wld": "WLD", "world": "WLD", "global": "WLD",
    "pk": "PK", "psx": "PK", "pakistan": "PK",
    "in": "IN", "nse": "IN", "bse": "IN", "india": "IN",
    "cn": "CN", "china": "CN",
}


def _geo(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return _GEO_ALIASES.get(raw.strip().lower(), raw.strip().upper())


def resolve_macro_series(series_id: str, geography: Optional[str] = None) -> dict[str, Any]:
    """Resolve a macro request to a canonical identity or a typed failure.

    Returns {"ok": True, "identity": {...}} or
    {"ok": False, "reason": ..., "message": ..., "candidates": [...]}.
    """
    raw = (series_id or "").strip()
    if not raw:
        return {"ok": False, "reason": "not_found", "message": "A macro series id is required."}

    geo = _geo(geography)

    by_id = next((s for s in _SERIES if s["id"].lower() == raw.lower()), None)
    if by_id:
        return {"ok": True, "identity": by_id}

    by_provider = [s for s in _SERIES if s["providerSeries"].lower() == raw.lower()]
    if len(by_provider) == 1:
        return {"ok": True, "identity": by_provider[0]}
    if len(by_provider) > 1:
        return {
            "ok": False,
            "reason": "ambiguous",
            "message": f'"{raw}" matches multiple series.',
            "candidates": [s["id"] for s in by_provider],
        }

    family = _GENERIC_MEASURE_FAMILIES.get(raw.lower().replace(" ", "_"))
    if family:
        if not geo:
            return {
                "ok": False,
                "reason": "ambiguous",
                "message": (
                    f'"{raw}" is generic and must be scoped to a geography '
                    '(e.g. "US policy rate" vs "ECB policy rate").'
                ),
                "candidates": [s["id"] for s in _SERIES if s["measure"] in family],
            }
        scoped = [s for s in _SERIES if s["geography"] == geo and s["measure"] in family]
        if not scoped:
            return {
                "ok": False,
                "reason": "not_covered",
                "message": f'No "{raw}" series is registered for {geo}.',
            }
        if len(scoped) > 1:
            return {
                "ok": False,
                "reason": "ambiguous",
                "message": (
                    f'"{raw}" on {geo} could mean any of several measures '
                    f'({", ".join(s["measure"] for s in scoped)}). Specify the measure.'
                ),
                "candidates": [s["id"] for s in scoped],
            }
        return {"ok": True, "identity": scoped[0]}

    # Unknown id with a known geography: pass through, never route to US by default.
    if geo:
        return {
            "ok": True,
            "identity": {
                "id": f"{geo}:?:{raw.upper()}",
                "geography": geo,
                "institution": "unknown",
                "measure": raw.lower(),
                "adjustment": "unknown",
                "frequency": "unknown",
                "sourceId": "",
                "providerSeries": raw,
            },
        }

    return {
        "ok": False,
        "reason": "ambiguous",
        "message": f'"{raw}" is not a known series and no geography was supplied.',
    }


__all__ = ["resolve_macro_series"]
