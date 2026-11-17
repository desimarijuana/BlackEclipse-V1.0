"""Deterministic scoring: turn measurements into a ranked research queue.

Everything here is arithmetic over observations. There is no model call, no
learned weight, and no hidden state — given the same observations this module
returns the same priorities, which is what makes a card reproducible and
arguable.

The score is a **triage priority in [0, 1]**, explicitly not a probability and
not an expected return. Its only job is ordering "what should I read first".
Every opportunity carries a thesis built from the real numbers and an
invalidation rule, so a wrong call is legible rather than mysterious.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

from .contracts import (
    ACTIVIST_STAKE,
    ATTENTION_VELOCITY,
    BEARISH,
    BULLISH,
    FILING_HEAT,
    HIGH,
    INSIDER_CONVICTION,
    LOW,
    MEDIUM,
    WATCH,
    Observation,
    Opportunity,
)

#: Base weights. They sum to 1.0 when every signal is present and are
#: re-normalised over the signals that actually fired, so a missing signal
#: lowers confidence instead of silently scoring zero.
WEIGHTS: dict[str, float] = {
    INSIDER_CONVICTION: 0.45,
    ACTIVIST_STAKE: 0.15,
    FILING_HEAT: 0.15,
    ATTENTION_VELOCITY: 0.25,
}

#: A signal only contributes when its own gate passes. Below these thresholds
#: the observation is still STORED (it is a measurement) but does not move a
#: priority — a quiet week should produce no card.
GATES: dict[str, float] = {
    ATTENTION_VELOCITY: 2.0,   # |robust z|
    FILING_HEAT: 2.0,          # ratio vs own baseline
}

HORIZONS: dict[str, int] = {
    INSIDER_CONVICTION: 60,
    ACTIVIST_STAKE: 120,
    FILING_HEAT: 30,
    ATTENTION_VELOCITY: 10,
}


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def log_scale(value: float, ceiling: float) -> float:
    """0 at 0, 1 at (or above) `ceiling`, logarithmic in between.

    Dollar amounts span orders of magnitude, so a linear scale would make every
    ordinary buy indistinguishable from noise and only a $100M buy visible.
    """
    if value <= 0 or ceiling <= 0:
        return 0.0
    return clamp01(math.log10(1.0 + value) / math.log10(1.0 + ceiling))


def recency(days: int) -> float:
    if days <= 7:
        return 1.0
    if days <= 30:
        return 0.7
    if days <= 60:
        return 0.4
    return 0.2


# ── Per-signal scores ───────────────────────────────────────────────────────

def score_insider(summary: dict[str, Any], *, as_of_days: int = 0) -> tuple[float, str, str]:
    """Score an insider summary. Returns (score, direction, why).

    `as_of_days` is how many days old the most recent actionable trade is; the
    caller computes it (the engine never reads a clock).
    """
    buyers = list(summary.get("buyers") or [])
    sellers = list(summary.get("sellers") or [])
    officers = list(summary.get("officerBuyers") or [])
    buy_usd = float(summary.get("buyUsd") or 0.0)
    sell_usd = float(summary.get("sellUsd") or 0.0)
    net = buy_usd - sell_usd

    buy_score = 0.0
    if buyers and buy_usd > 0:
        buy_score = (
            0.35 * clamp01(len(buyers) / 3.0)
            + 0.35 * log_scale(buy_usd, 10_000_000.0)
            + 0.15 * clamp01(len(officers) / 2.0)
            + 0.15 * recency(as_of_days)
        )

    sell_score = 0.0
    if len(sellers) >= 2 and sell_usd > 0:
        sell_score = (
            0.40 * clamp01(len(sellers) / 3.0)
            + 0.40 * log_scale(sell_usd, 20_000_000.0)
            + 0.20 * recency(as_of_days)
        )

    if net > 0 and buy_score >= sell_score:
        why = (
            f"{len(buyers)} insider(s) bought ${buy_usd:,.0f} of stock in the "
            f"window ({len(officers)} officer/director)"
        )
        if sell_usd > 0:
            why += f" against ${sell_usd:,.0f} of unplanned sales"
        return clamp01(buy_score), BULLISH, why
    if net < 0 and sell_score > 0:
        why = f"{len(sellers)} insider(s) sold ${sell_usd:,.0f} with no offsetting unplanned buying"
        return clamp01(sell_score), BEARISH, why
    if buy_score > 0:
        return clamp01(buy_score), WATCH, (
            f"insiders bought ${buy_usd:,.0f} but unplanned sales (${sell_usd:,.0f}) dominate"
        )
    return 0.0, WATCH, "no unplanned insider transactions in the window"


def score_attention(reading: dict[str, Any]) -> tuple[float, str, str]:
    """Score an attention reading. Direction is always WATCH on its own.

    Attention is a *prompt*, not a thesis: the same spike precedes a squeeze and
    a top. Only its interaction with price (see `divergence`) is interpretable,
    which is why this signal contributes score but no direction.
    """
    z = float(reading.get("zscore") or 0.0)
    ratio = float(reading.get("ratio") or 0.0)
    gate = GATES[ATTENTION_VELOCITY]
    if abs(z) < gate:
        return 0.0, WATCH, f"attention is within its own normal range (z={z:+.1f})"
    strength = clamp01((abs(z) - gate) / 2.0) * (0.6 + 0.4 * clamp01(abs(math.log(max(ratio, 1e-6)))))
    verb = "surged" if z > 0 else "faded"
    return clamp01(strength), WATCH, (
        f"Wikipedia attention {verb} to {ratio:.1f}x its own baseline (robust z={z:+.1f})"
    )


def score_activist(count: int) -> tuple[float, str, str]:
    if count <= 0:
        return 0.0, WATCH, ""
    score = clamp01(0.5 + 0.2 * min(count, 3))
    return score, WATCH, f"{count} Schedule 13D filing(s) in the window (declared intent to influence)"


def score_filing_heat(ratio: float) -> tuple[float, str, str]:
    if ratio < GATES[FILING_HEAT]:
        return 0.0, WATCH, ""
    score = clamp01((ratio - 1.0) / 3.0)
    return score, WATCH, f"filing pace is {ratio:.1f}x this company's own trailing rate"


def divergence(price_context: Optional[dict[str, Any]], reading: Optional[dict[str, Any]]) -> str:
    """A plain-English read of signal-vs-price, or '' when price is unknown."""
    if not price_context or not reading:
        return ""
    z = float(reading.get("zscore") or 0.0)
    ret5 = price_context.get("change5d")
    ret30 = price_context.get("change30d")
    if z >= 2 and ret5 is not None:
        if -0.02 <= float(ret5) <= 0.02:
            return "attention is rising while the price is flat — a possible underreaction"
        if float(ret5) > 0.10:
            return "attention and price are already moving together — likely already priced"
    if z <= -2 and ret30 is not None and float(ret30) < 0:
        return "attention is fading alongside price weakness — no fresh interest is arriving"
    return ""


def insider_price_note(price_context: Optional[dict[str, Any]], direction: str) -> str:
    if not price_context or direction != BULLISH:
        return ""
    ret30 = price_context.get("change30d")
    if ret30 is None:
        return ""
    if float(ret30) <= -0.10:
        return "insiders are buying into weakness"
    if float(ret30) >= 0.20:
        return "insiders are buying after a 30-day run-up — check the entry point"
    return ""


# ── Assembly ────────────────────────────────────────────────────────────────

def build_opportunity(
    entity: str,
    observations: Iterable[dict[str, Any]],
    *,
    as_of: str,
    price_context: Optional[dict[str, Any]] = None,
    days_since_last_buy: int = 0,
) -> Optional[Opportunity]:
    """Assemble one card from an entity's observations, or None if quiet.

    `observations` are `Observation.to_dict()`-shaped. A card is emitted only
    when a directional signal or a gated event fired; otherwise silence.
    """
    obs = [o for o in observations if str(o.get("entity") or "").upper() == entity.upper()]
    if not obs:
        return None

    by_signal = {str(o["signal"]): o for o in obs if isinstance(o, dict)}
    scored: list[dict[str, Any]] = []
    directions: list[str] = []
    sources: list[str] = []
    why: list[str] = []
    caveats: list[str] = []
    observations_caveats = {str(o["signal"]): str(o.get("note") or "") for o in obs}

    insider = by_signal.get(INSIDER_CONVICTION)
    if insider:
        value = insider.get("detail") or {}
        summary = value if isinstance(value, dict) else {}
        s, d, reason = score_insider(summary, as_of_days=days_since_last_buy)
        if s > 0:
            scored.append({"signal": INSIDER_CONVICTION, "score": s, "direction": d, "why": reason})
            why.append(reason)
            if d != WATCH:
                directions.append(d)

    activist = by_signal.get(ACTIVIST_STAKE)
    if activist:
        s, d, reason = score_activist(int(float(activist.get("value") or 0)))
        if s > 0:
            scored.append({"signal": ACTIVIST_STAKE, "score": s, "direction": d, "why": reason})
            why.append(reason)

    heat = by_signal.get(FILING_HEAT)
    if heat:
        s, d, reason = score_filing_heat(float(heat.get("value") or 0.0))
        if s > 0:
            scored.append({"signal": FILING_HEAT, "score": s, "direction": d, "why": reason})
            why.append(reason)

    attention = by_signal.get(ATTENTION_VELOCITY)
    reading = (attention.get("detail") if attention else None) or None
    if isinstance(reading, dict):
        s, d, reason = score_attention(reading)
        if s > 0:
            scored.append({"signal": ATTENTION_VELOCITY, "score": s, "direction": d, "why": reason})
            why.append(reason)

    if not scored:
        return None

    # Direction: a directional call needs a directional signal. Everything else
    # is a "watch" — an event worth reading, with no side claimed.
    bullish = directions.count(BULLISH)
    bearish = directions.count(BEARISH)
    if bullish > bearish:
        direction = BULLISH
    elif bearish > bullish:
        direction = BEARISH
    else:
        direction = WATCH

    # Weighted priority over the signals that fired, evidence-adjusted.
    total_weight = 0.0
    weighted = 0.0
    for item in scored:
        obs_conf = float((by_signal[item["signal"]] or {}).get("confidence") or 0.5)
        w = WEIGHTS.get(item["signal"], 0.1)
        total_weight += w
        weighted += w * item["score"] * (0.6 + 0.4 * clamp01(obs_conf))
    priority = weighted / total_weight if total_weight else 0.0

    # Corroboration: distinct publishers matter more than a repeated signal.
    distinct_sources = {
        str(by_signal[item["signal"]].get("source") or "")
        for item in scored if item["signal"] in by_signal
    } - {""}
    if len(distinct_sources) >= 2 and direction != WATCH:
        priority = clamp01(priority + 0.10)
    priority = clamp01(priority)

    # Conviction is about CORROBORATION, not intensity: one very loud signal is
    # still one signal, so it stays `low` no matter how high its priority. This
    # is what keeps a single attention spike from reading as a strong call.
    if len(distinct_sources) >= 2 and priority >= 0.60:
        conviction = HIGH
    elif len(distinct_sources) >= 2:
        conviction = MEDIUM
    else:
        conviction = LOW

    dominant = max(scored, key=lambda item: WEIGHTS.get(item["signal"], 0.1) * item["score"])
    horizon = HORIZONS.get(dominant["signal"], 30)

    thesis_parts = [item["why"] for item in scored]
    price_note = divergence(price_context, reading if isinstance(reading, dict) else None)
    if price_note:
        thesis_parts.append(price_note)
    buy_note = insider_price_note(price_context, direction)
    if buy_note:
        thesis_parts.append(buy_note)

    invalidation = _invalidation_for(scored, direction)
    caveats.extend(_caveats_for(scored, observations_caveats))

    return Opportunity(
        entity=entity.upper(),
        direction=direction,
        priority=priority,
        conviction=conviction,
        horizon_days=horizon,
        thesis="; ".join(part for part in thesis_parts if part) + ".",
        invalidation=invalidation,
        signals=[
            {
                "signal": item["signal"],
                "score": round(item["score"], 3),
                "direction": item["direction"],
                "weight": WEIGHTS.get(item["signal"], 0.1),
                "why": item["why"],
                "asOf": (by_signal.get(item["signal"]) or {}).get("asOf"),
                "source": (by_signal.get(item["signal"]) or {}).get("source"),
            }
            for item in scored
        ],
        sources=sorted(distinct_sources),
        price_context=price_context,
        caveats=caveats,
        as_of=as_of,
    )


def _invalidation_for(scored: list[dict[str, Any]], direction: str) -> str:
    rules: list[str] = []
    ids = {item["signal"] for item in scored}
    if INSIDER_CONVICTION in ids:
        rules.append(
            "insiders reverse (a new unplanned sale larger than the observed buying) "
            "or a filing amendment withdraws the reported purchases"
        )
    if ATTENTION_VELOCITY in ids:
        rules.append("attention returns within one robust sigma of baseline")
    if ACTIVIST_STAKE in ids:
        rules.append("the 13D is amended down/withdrawn or a settlement is disclosed")
    if FILING_HEAT in ids:
        rules.append("the elevated filing pace falls back to its trailing rate")
    if not rules:
        rules.append("the underlying measurement falls back below its gate")
    if direction == WATCH:
        return "This is a watch item, not a directional call. Close it when: " + "; ".join(rules) + "."
    return "Close the case when: " + "; ".join(rules) + "."


def _caveats_for(scored: list[dict[str, Any]], notes: dict[str, str]) -> list[str]:
    from .contracts import SIGNALS

    out: list[str] = []
    for item in scored:
        spec = SIGNALS.get(item["signal"])
        if spec is not None:
            out.append(f"{spec.label}: {spec.limit}")
        note = notes.get(item["signal"]) or ""
        if note:
            out.append(note)
    return out


def rank(opportunities: Iterable[Opportunity], limit: int = 10) -> list[Opportunity]:
    """Newest-agnostic, highest-priority-first, ties broken by entity."""
    ordered = sorted(opportunities, key=lambda o: (-o.priority, o.entity))
    return ordered[: max(1, int(limit))]


__all__ = [
    "GATES", "HORIZONS", "WEIGHTS", "build_opportunity", "clamp01", "divergence",
    "insider_price_note", "log_scale", "rank", "recency", "score_activist",
    "score_attention", "score_filing_heat", "score_insider",
]
