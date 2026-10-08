"""Black-Scholes option pricing + Greeks (derived analytics).

Yahoo supplies implied volatility but NOT Greeks. Rather than present a Greek as
zero (forbidden), Eclipse CALCULATES them from the provider's implied vol and the
chain's underlying price, and labels the result `greeks_source="calculated"`.
A provider-supplied Greek always wins.

Model assumptions (documented, not hidden): European exercise, no dividends,
constant risk-free rate, constant volatility. `price` is the theoretical value
(the provider's market price is kept separately).

Pure math, no I/O. A missing input yields `None` — never a fabricated number.
"""

from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Optional

# Default risk-free rate used ONLY when the caller does not supply one. An
# operator can override it (HARNESS_MARKET_RISK_FREE) or pass the 10Y yield.
DEFAULT_RISK_FREE = 0.04


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def years_to_expiry(expiration: Optional[str], *, now: Optional[_dt.datetime] = None) -> Optional[float]:
    """Calendar years from now to an ISO date/timestamp, or None."""
    if not expiration:
        return None
    text = str(expiration).strip()
    parsed: Optional[_dt.datetime] = None
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = _dt.datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = _dt.datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    ref = now or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    days = (parsed - ref).total_seconds() / 86400.0
    return max(0.0, days / 365.0)


def black_scholes(
    *,
    option_type: str,
    spot: float,
    strike: float,
    time_to_expiry: float,
    iv: float,
    risk_free: float = DEFAULT_RISK_FREE,
    dividend_yield: float = 0.0,
) -> Optional[dict[str, float]]:
    """Price + Greeks for one European option. None when inputs are unusable."""
    if not (spot > 0 and strike > 0 and iv > 0):
        return None
    if time_to_expiry <= 0:
        # At/after expiry a Greek is meaningless; return intrinsic delta only is
        # also misleading — return None so the caller reports "unavailable".
        return None
    t = time_to_expiry
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (risk_free - dividend_yield + 0.5 * iv * iv) * t) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t
    disc_r = math.exp(-risk_free * t)
    disc_q = math.exp(-dividend_yield * t)
    call = option_type.lower().startswith("c")
    if call:
        price = spot * disc_q * _norm_cdf(d1) - strike * disc_r * _norm_cdf(d2)
        delta = disc_q * _norm_cdf(d1)
        rho = strike * t * disc_r * _norm_cdf(d2) / 100.0
    else:
        price = strike * disc_r * _norm_cdf(-d2) - spot * disc_q * _norm_cdf(-d1)
        delta = -disc_q * _norm_cdf(-d1)
        rho = -strike * t * disc_r * _norm_cdf(-d2) / 100.0
    gamma = disc_q * _norm_pdf(d1) / (spot * iv * sqrt_t)
    vega = spot * disc_q * _norm_pdf(d1) * sqrt_t / 100.0
    # Theta per calendar day (convention: /365).
    theta_common = -(spot * disc_q * _norm_pdf(d1) * iv) / (2 * sqrt_t)
    if call:
        theta = (theta_common - risk_free * strike * disc_r * _norm_cdf(d2)
                 + dividend_yield * spot * disc_q * _norm_cdf(d1)) / 365.0
    else:
        theta = (theta_common + risk_free * strike * disc_r * _norm_cdf(-d2)
                 - dividend_yield * spot * disc_q * _norm_cdf(-d1)) / 365.0
    return {
        "price": price, "delta": delta, "gamma": gamma,
        "theta": theta, "vega": vega, "rho": rho,
    }


def enrich_options_greeks(
    chain: Any,
    *,
    risk_free: float = DEFAULT_RISK_FREE,
    now: Optional[_dt.datetime] = None,
) -> int:
    """Fill missing Greeks on an OptionsChain in place. Returns how many filled.

    A provider-supplied Greek is never overwritten. A contract with insufficient
    inputs keeps `None` (reported as unavailable, never zero).
    """
    spot = getattr(chain, "underlying_price", None)
    filled = 0
    for contract in getattr(chain, "contracts", []) or []:
        if all(getattr(contract, g, None) is not None for g in ("delta", "gamma", "theta", "vega", "rho")):
            continue
        if spot is None or contract.strike is None or contract.implied_volatility is None:
            continue
        t = years_to_expiry(contract.expiration, now=now)
        if t is None:
            continue
        greeks = black_scholes(
            option_type=contract.option_type, spot=float(spot), strike=float(contract.strike),
            time_to_expiry=t, iv=float(contract.implied_volatility), risk_free=risk_free,
        )
        if greeks is None:
            continue
        if contract.delta is None:
            contract.delta = greeks["delta"]
        if contract.gamma is None:
            contract.gamma = greeks["gamma"]
        if contract.theta is None:
            contract.theta = greeks["theta"]
        if contract.vega is None:
            contract.vega = greeks["vega"]
        if contract.rho is None:
            contract.rho = greeks["rho"]
        contract.greeks_source = contract.greeks_source or "calculated(black-scholes, no-dividend)"
        filled += 1
    return filled


__all__ = ["DEFAULT_RISK_FREE", "black_scholes", "enrich_options_greeks", "years_to_expiry"]
