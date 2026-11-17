"""The intelligence vocabulary: one observation, one signal, one opportunity.

Three rules shape this module, and every collector obeys them:

  * **An observation is a measurement, not a mood.** It carries the exact
    window, the source, the deterministic method and the provenance needed to
    re-derive it. No model is involved in producing one.
  * **Absence is `UNAVAILABLE`, never zero.** A company with no insider filings
    in the window has NO observation; a zero would read as "measured calm",
    which would be a lie.
  * **A priority score is triage, not a probability, and not expected return.**
    It orders a research queue. Nothing here converts a score into a trade.

This module is pure data + pure functions: no I/O, no clock, no network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── The closed signal vocabulary ────────────────────────────────────────────
# Adding a signal means adding a `SignalSpec` here AND a collector that emits
# the id. The engine refuses to score an id it does not know.
INSIDER_CONVICTION = "insider_conviction"
ACTIVIST_STAKE = "activist_stake"
FILING_HEAT = "filing_heat"
ATTENTION_VELOCITY = "attention_velocity"

SIGNAL_IDS: tuple[str, ...] = (
    INSIDER_CONVICTION,
    ACTIVIST_STAKE,
    FILING_HEAT,
    ATTENTION_VELOCITY,
)

# ── Directions ──────────────────────────────────────────────────────────────
BULLISH = "bullish"
BEARISH = "bearish"
WATCH = "watch"  # a change worth reading, with no directional claim
DIRECTIONS: tuple[str, ...] = (BULLISH, BEARISH, WATCH)

# ── Conviction buckets (how much corroboration the card has) ────────────────
HIGH = "high"
MEDIUM = "medium"
LOW = "low"
CONVICTIONS: tuple[str, ...] = (HIGH, MEDIUM, LOW)


@dataclass(frozen=True)
class SignalSpec:
    """What a signal means, where it comes from, and how it can be wrong."""

    id: str
    label: str
    question: str  # the human question it answers
    source: str
    unit: str
    default_direction: str
    rationale: str
    limit: str  # the honest failure mode
    min_history_days: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "question": self.question,
            "source": self.source,
            "unit": self.unit,
            "defaultDirection": self.default_direction,
            "rationale": self.rationale,
            "limit": self.limit,
            "minHistoryDays": self.min_history_days,
        }


#: The catalogue. `limit` is not boilerplate — it is the caveat the agent MUST
#: repeat when it uses the signal, so a card never overstates its evidence.
SIGNALS: dict[str, SignalSpec] = {
    INSIDER_CONVICTION: SignalSpec(
        id=INSIDER_CONVICTION,
        label="Insider conviction (opportunistic)",
        question="Are insiders putting their own money in, or only selling on autopilot?",
        source="sec-edgar",
        unit="usd",
        default_direction=BULLISH,
        rationale=(
            "Open-market purchases (Form 4 code P) by officers and directors are the "
            "highest-signal insider action: they spend real money at a real price. "
            "Sales are weakly informative because they are dominated by diversification "
            "and pre-scheduled 10b5-1 plans, so planned sales, option exercises, grants "
            "and tax withholding are excluded rather than netted in."
        ),
        limit=(
            "Form 4 is filed within two business days, but a filing can be amended or "
            "mis-coded, and a purchase can reflect portfolio rebalancing by a control "
            "person rather than a view on value. A cluster is evidence, not proof."
        ),
    ),
    ACTIVIST_STAKE: SignalSpec(
        id=ACTIVIST_STAKE,
        label="Activist / control stake",
        question="Has a large holder crossed 5% with intent to influence?",
        source="sec-edgar",
        unit="count",
        default_direction=WATCH,
        rationale=(
            "A Schedule 13D (unlike 13G) is filed when the holder intends to influence "
            "control, which historically precedes board pressure, buybacks, spin-offs "
            "or a sale process."
        ),
        limit=(
            "The stake may already be public and priced, the 13D may be amended "
            "repeatedly without a new position, and intent is not a plan. Some 13Ds "
            "are defensive or creditor-driven."
        ),
    ),
    FILING_HEAT: SignalSpec(
        id=FILING_HEAT,
        label="Filing intensity",
        question="Is this company suddenly filing far more than its own normal?",
        source="sec-edgar",
        unit="ratio",
        default_direction=WATCH,
        rationale=(
            "A company's 8-K/4 cadence is a fingerprint. A jump against its own trailing "
            "baseline often precedes or accompanies a material event (financing, "
            "restatement, deal, management change) that has not yet been narrated."
        ),
        limit=(
            "Late/quarterly clusters (proxy season, 10-K exhibits) inflate the count "
            "seasonally. The ratio is against the same company's own history, not the "
            "market's, and a single month is a small sample."
        ),
    ),
    ATTENTION_VELOCITY: SignalSpec(
        id=ATTENTION_VELOCITY,
        label="Public attention velocity",
        question="Is public attention to this company changing faster than its price?",
        source="wikipedia",
        unit="zscore",
        default_direction=WATCH,
        rationale=(
            "English Wikipedia daily pageviews are a free, stable, bot-filtered proxy for "
            "retail attention and curiosity. Attention shocks lead flows in small caps far "
            "more than in mega caps, and large-cap articles are dominated by routine "
            "traffic, so the signal is most meaningful where it fires hardest."
        ),
        limit=(
            "Pageviews measure curiosity, not buying, and are polluted by news events, "
            "bot traffic that survives filtering, and page moves. A z-score against the "
            "article's own history says nothing about direction by itself."
        ),
        min_history_days=30,
    ),
}


def get_signal(signal_id: str) -> Optional[SignalSpec]:
    return SIGNALS.get(str(signal_id or "").strip())


def signal_catalog() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in SIGNALS.values()]


@dataclass(frozen=True)
class Observation:
    """One deterministic measurement about one entity at one point in time."""

    entity: str
    signal: str
    as_of: str  # ISO date (YYYY-MM-DD)
    value: float  # the one numeric series point (sorts, charts, compares)
    unit: str
    window_days: int
    confidence: float  # 0..1 — evidence quality, NOT conviction
    source: str
    method: str  # a short sentence a reader can reproduce
    #: The full measurement behind `value` (counts, names, ratios). Kept
    #: separate so the numeric series stays uniform while a card can quote the
    #: actual evidence. Never a model output.
    detail: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    direction_hint: str = WATCH
    note: str = ""

    def key(self) -> str:
        """Deterministic identity: a re-scan updates, it does not duplicate."""
        return f"{self.entity.upper()}|{self.signal}|{self.as_of}|{int(self.window_days)}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "signal": self.signal,
            "asOf": self.as_of,
            "value": self.value,
            "unit": self.unit,
            "windowDays": self.window_days,
            "confidence": round(float(self.confidence), 3),
            "source": self.source,
            "method": self.method,
            "detail": self.detail,
            "provenance": self.provenance,
            "directionHint": self.direction_hint,
            "note": self.note,
        }


@dataclass(frozen=True)
class Opportunity:
    """A research lead: what fired, why, and what would prove it wrong."""

    entity: str
    direction: str
    priority: float  # 0..1 triage ordering, never an expected return
    conviction: str
    horizon_days: int
    thesis: str
    invalidation: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    price_context: Optional[dict[str, Any]] = None
    caveats: list[str] = field(default_factory=list)
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity,
            "direction": self.direction,
            "priority": round(float(self.priority), 3),
            "conviction": self.conviction,
            "horizonDays": self.horizon_days,
            "thesis": self.thesis,
            "invalidation": self.invalidation,
            "signals": self.signals,
            "sources": self.sources,
            "priceContext": self.price_context,
            "caveats": self.caveats,
            "asOf": self.as_of,
        }


__all__ = [
    "ACTIVIST_STAKE", "ATTENTION_VELOCITY", "BEARISH", "BULLISH", "CONVICTIONS",
    "FILING_HEAT", "HIGH", "INSIDER_CONVICTION", "LOW", "MEDIUM", "Observation",
    "Opportunity", "SIGNALS", "SIGNAL_IDS", "SignalSpec", "WATCH", "DIRECTIONS",
    "get_signal", "signal_catalog",
]
