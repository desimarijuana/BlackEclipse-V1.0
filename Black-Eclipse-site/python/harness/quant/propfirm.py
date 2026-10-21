"""Prop-firm evaluation rules — the constraints a funded account must survive.

A *prop firm* sells a funded account for a fee, and the fee is only worth
paying if the trader can reach the profit target **without breaching the risk
limits**. This module encodes those limits as data, so a trade log can be
tested against them honestly and repeatedly, instead of once by eye.

Three properties matter and are enforced here:

1. **The rules are data, not code.** Every limit — profit target, maximum
   loss, daily loss limit, consistency rule, access period, payout split — is a
   field on a spec. A firm the engine does not know about is still supported:
   the caller passes their own spec.
2. **Every spec is sourced and dated.** A spec carries `source` and `as_of`.
   Firm rules change constantly, so the engine reports the spec it used and
   warns that the trader must confirm it against the firm's own page. The
   engine never pretends a built-in spec is current.
3. **The simulation states its own blindness.** Prop firms liquidate on
   *intraday* equity, including unrealised P&L. A log of closed trades cannot
   see an intraday drawdown that recovered before the close. The engine checks
   what it can (realised balance, trade by trade, inside a day) and says
   plainly that intraday equity is not modelled.

The engine is a **constraint checker**, not a predictor: it reports what the
rules would have done to *this* sequence of trades. `propfirm_mc.py` adds the
uncertainty by resampling it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import QuantError


class PropFirmError(QuantError):
    code = "PROP_FIRM_ERROR"


#: How the maximum-loss threshold moves.
MAX_LOSS_MODES = (
    "trailing_never_down",   # trails on end-of-day balance, never moves down
    "eod_recalculated",      # recalculated once per day from the previous close
    "static_from_start",     # a fixed distance below the starting balance
)

#: What happens when the daily loss limit is hit.
DAILY_LOSS_ACTIONS = ("breach", "session_break")

#: What a consistency violation does.
CONSISTENCY_ACTIONS = ("breach", "warn", "raise_target")

#: What the consistency rule is measured against.
CONSISTENCY_MEASURES = ("profit_target", "total_profit")


@dataclass(frozen=True)
class PropAccountSize:
    """One purchasable account size of one firm."""

    id: str
    label: str
    account_size: float
    profit_target: float
    max_loss: float
    daily_loss_limit: Optional[float] = None
    min_trading_days: int = 0
    max_trading_days: Optional[int] = None      # access period, in calendar days
    max_contracts: Optional[int] = None
    notes: str = ""


@dataclass(frozen=True)
class PropPhaseRules:
    """The rules of one phase (evaluation, funded)."""

    id: str
    profit_target: Optional[float] = None
    has_profit_target: bool = False
    max_loss: float = 0.0
    max_loss_mode: str = "trailing_never_down"
    max_loss_ceiling: Optional[float] = None   # static ceiling above the start
    daily_loss_limit: Optional[float] = None
    daily_loss_action: str = "session_break"
    min_trading_days: int = 0
    max_trading_days: Optional[int] = None
    consistency_share: Optional[float] = None
    consistency_measure: str = "profit_target"
    consistency_action: str = "warn"
    payout_split: float = 1.0
    payout_cap: Optional[float] = None
    payout_share_of_balance: float = 1.0
    min_payout: Optional[float] = None
    payout_frequency_days: Optional[int] = None
    min_profitable_days: int = 0
    min_profitable_day_amount: float = 0.0

    def validate(self) -> None:
        if self.max_loss_mode not in MAX_LOSS_MODES:
            raise PropFirmError(f"unknown max loss mode {self.max_loss_mode!r}")
        if self.daily_loss_action not in DAILY_LOSS_ACTIONS:
            raise PropFirmError(f"unknown daily loss action {self.daily_loss_action!r}")
        if self.consistency_action not in CONSISTENCY_ACTIONS:
            raise PropFirmError(f"unknown consistency action {self.consistency_action!r}")
        if self.consistency_measure not in CONSISTENCY_MEASURES:
            raise PropFirmError(
                f"unknown consistency measure {self.consistency_measure!r}")
        if not (0.0 < self.payout_split <= 1.0):
            raise PropFirmError("payout_split must be in (0, 1]")


@dataclass(frozen=True)
class PropFirmSpec:
    """A firm's evaluation rules plus its funded-account rules."""

    id: str
    name: str
    source: str
    as_of: str
    evaluation: PropPhaseRules
    funded: PropPhaseRules
    sizes: tuple[PropAccountSize, ...]
    day_offset_hours: int = 0
    session_note: str = ""
    notes: str = ""

    def validate(self) -> None:
        self.evaluation.validate()
        self.funded.validate()
        if not self.sizes:
            raise PropFirmError(f"{self.id}: no account sizes")
        for size in self.sizes:
            if size.account_size <= 0:
                raise PropFirmError(f"{self.id}/{size.id}: account size must be > 0")
            if size.profit_target <= 0:
                raise PropFirmError(f"{self.id}/{size.id}: profit target must be > 0")
            if size.max_loss <= 0:
                raise PropFirmError(f"{self.id}/{size.id}: max loss must be > 0")
            if size.max_loss >= size.account_size:
                raise PropFirmError(
                    f"{self.id}/{size.id}: max loss must be below the account size")
            if size.max_trading_days is not None and size.max_trading_days < 1:
                raise PropFirmError(f"{self.id}/{size.id}: max_trading_days must be >= 1")

    def size(self, size_id: str) -> PropAccountSize:
        for candidate in self.sizes:
            if candidate.id.lower() == str(size_id).lower():
                return candidate
        raise PropFirmError(
            f"{self.id} has no account size {size_id!r}",
            detail={"available": [s.id for s in self.sizes]},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "asOf": self.as_of,
            "dayOffsetHours": self.day_offset_hours,
            "sessionNote": self.session_note,
            "notes": self.notes,
            "sizes": [
                {
                    "id": s.id, "label": s.label, "accountSize": s.account_size,
                    "profitTarget": s.profit_target, "maxLoss": s.max_loss,
                    "dailyLossLimit": s.daily_loss_limit,
                    "minTradingDays": s.min_trading_days,
                    "maxTradingDays": s.max_trading_days,
                    "maxContracts": s.max_contracts, "notes": s.notes,
                }
                for s in self.sizes
            ],
            "evaluation": _phase_to_dict(self.evaluation),
            "funded": _phase_to_dict(self.funded),
        }


def _phase_to_dict(phase: PropPhaseRules) -> dict[str, Any]:
    return {
        "id": phase.id,
        "profitTarget": phase.profit_target,
        "hasProfitTarget": phase.has_profit_target,
        "maxLoss": phase.max_loss,
        "maxLossMode": phase.max_loss_mode,
        "maxLossCeiling": phase.max_loss_ceiling,
        "dailyLossLimit": phase.daily_loss_limit,
        "dailyLossAction": phase.daily_loss_action,
        "minTradingDays": phase.min_trading_days,
        "maxTradingDays": phase.max_trading_days,
        "consistencyShare": phase.consistency_share,
        "consistencyMeasure": phase.consistency_measure,
        "consistencyAction": phase.consistency_action,
        "payoutSplit": phase.payout_split,
        "payoutCap": phase.payout_cap,
        "payoutShareOfBalance": phase.payout_share_of_balance,
        "minPayout": phase.min_payout,
        "payoutFrequencyDays": phase.payout_frequency_days,
        "minProfitableDays": phase.min_profitable_days,
        "minProfitableDayAmount": phase.min_profitable_day_amount,
    }


# ── The built-in specs ───────────────────────────────────────────────────────
#
# Every number below was read from the firm's own published page (see `source`)
# on the date in `as_of`. Firm rules change often: the engine reports the spec
# it used and tells the trader to confirm it. A size that is not encoded is
# reported as unavailable, never guessed.

TOPSTEP = PropFirmSpec(
    id="topstep",
    name="Topstep Trading Combine / Express Funded Account",
    source="help.topstep.com (Maximum Loss Limit; Trading Combine Parameters; "
           "Daily Loss Limit) and topstep.com/no-activation-fee",
    as_of="2026-10-20",
    day_offset_hours=-6,   # the trading day runs 17:00 CT to 16:10 CT
    session_note="Topstep's trading day runs 17:00 CT to 16:10 CT. The day "
                 "boundary is approximated with a fixed -6h offset (daylight "
                 "saving is not modelled), so day-level results are approximate.",
    evaluation=PropPhaseRules(
        id="evaluation",
        has_profit_target=True,
        max_loss_mode="trailing_never_down",
        daily_loss_action="session_break",
        min_trading_days=2,
        consistency_share=0.55,
        consistency_measure="profit_target",
        consistency_action="raise_target",
    ),
    funded=PropPhaseRules(
        id="funded",
        max_loss_mode="trailing_never_down",
        daily_loss_action="session_break",
        payout_split=0.90,
        payout_cap=5_000.0,
        payout_share_of_balance=0.5,
        min_payout=125.0,
        min_profitable_days=5,
        min_profitable_day_amount=150.0,
    ),
    sizes=(
        PropAccountSize(id="50k", label="50K", account_size=50_000.0,
                         profit_target=3_000.0, max_loss=2_000.0,
                         daily_loss_limit=1_000.0, min_trading_days=2,
                         max_contracts=5,
                         notes="Maximum Loss Limit $2,000; Profit Target $3,000; "
                               "Daily Loss Limit $1,000 (optional at checkout, "
                               "not a rule breach)."),
        PropAccountSize(id="100k", label="100K", account_size=100_000.0,
                         profit_target=6_000.0, max_loss=3_000.0,
                         daily_loss_limit=2_000.0, min_trading_days=2,
                         max_contracts=10,
                         notes="Maximum Loss Limit $3,000; Profit Target $6,000; "
                               "Daily Loss Limit $2,000."),
        PropAccountSize(id="150k", label="150K", account_size=150_000.0,
                         profit_target=9_000.0, max_loss=4_500.0,
                         daily_loss_limit=3_000.0, min_trading_days=2,
                         max_contracts=15,
                         notes="Maximum Loss Limit $4,500; Profit Target $9,000; "
                               "Daily Loss Limit $3,000."),
    ),
    notes="The Maximum Loss Limit trails on the end-of-day balance, never moves "
          "down and locks once it reaches the starting balance; it is enforced "
          "in real time, including on unrealised P&L. The 55% consistency target "
          "raises the profit target rather than failing the account.",
)

APEX_EOD = PropFirmSpec(
    id="apex_eod",
    name="Apex Trader Funding — End-of-Day Evaluation / EOD Performance Account",
    source="apextraderfunding.com help centre (EOD Evaluations; EOD Performance "
           "Accounts)",
    as_of="2026-10-20",
    evaluation=PropPhaseRules(
        id="evaluation",
        has_profit_target=True,
        max_loss_mode="eod_recalculated",
        max_loss_ceiling=100.0,
        daily_loss_action="session_break",
        min_trading_days=0,
    ),
    funded=PropPhaseRules(
        id="funded",
        max_loss_mode="eod_recalculated",
        max_loss_ceiling=100.0,
        daily_loss_action="session_break",
        payout_split=1.0,
    ),
    sizes=(
        PropAccountSize(id="25k", label="25K", account_size=25_000.0,
                         profit_target=1_500.0, max_loss=1_000.0,
                         daily_loss_limit=500.0, max_trading_days=30,
                         max_contracts=4),
        PropAccountSize(id="50k", label="50K", account_size=50_000.0,
                         profit_target=3_000.0, max_loss=2_000.0,
                         daily_loss_limit=1_000.0, max_trading_days=30,
                         max_contracts=6),
        PropAccountSize(id="100k", label="100K", account_size=100_000.0,
                         profit_target=6_000.0, max_loss=3_000.0,
                         daily_loss_limit=1_500.0, max_trading_days=30,
                         max_contracts=8),
        PropAccountSize(id="150k", label="150K", account_size=150_000.0,
                         profit_target=9_000.0, max_loss=4_000.0,
                         daily_loss_limit=2_000.0, max_trading_days=30,
                         max_contracts=12),
    ),
    notes="The EOD drawdown is recalculated once per day at market close and is "
          "enforced during the following session; trailing stops once it "
          "reaches the starting balance + $100. Hitting the Daily Loss Limit "
          "pauses trading for the session and does NOT fail the evaluation. "
          "There is no minimum trading day and no consistency rule on the EOD "
          "evaluation. The EOD Performance Account pays out at 100%.",
)

FTMO_PRO = PropFirmSpec(
    id="ftmo_pro",
    name="FTMO Futures — 2-Step Challenge (Pro) / Sim-Funded Account",
    source="ftmo.com (Trading Objectives & Rules; How it works; "
           "academy.ftmo.com Maximum Daily Loss)",
    as_of="2026-10-20",
    evaluation=PropPhaseRules(
        id="evaluation",
        has_profit_target=True,
        max_loss_mode="static_from_start",
        daily_loss_action="breach",
        min_trading_days=0,
        consistency_share=0.50,
        consistency_measure="total_profit",
        consistency_action="breach",
    ),
    funded=PropPhaseRules(
        id="funded",
        max_loss_mode="static_from_start",
        daily_loss_action="breach",
        payout_split=0.90,
        payout_frequency_days=5,
        min_profitable_days=5,
    ),
    sizes=(
        PropAccountSize(id="50k", label="50K", account_size=50_000.0,
                         profit_target=3_000.0, max_loss=5_000.0,
                         daily_loss_limit=2_500.0,
                         notes="10% maximum loss and 5% maximum daily loss of the "
                               "initial simulated capital."),
        PropAccountSize(id="100k", label="100K", account_size=100_000.0,
                         profit_target=6_000.0, max_loss=10_000.0,
                         daily_loss_limit=5_000.0),
        PropAccountSize(id="150k", label="150K", account_size=150_000.0,
                         profit_target=9_000.0, max_loss=15_000.0,
                         daily_loss_limit=7_500.0),
    ),
    notes="The 2-Step maximum daily loss is 5% of the initial simulated capital, "
          "recalculated at midnight CE(S)T, so it can rise and fall. The Pro "
          "consistency rule caps the best day at 50% of total profit and IS a "
          "violation. The Sim-Funded account has no target and no consistency "
          "rule; payouts need 5 qualifying days and can be requested every 5 "
          "days at a 90% split.",
)

TPT_PRO = PropFirmSpec(
    id="tpt_pro",
    name="Take Profit Trader — Test Account / PRO Account",
    source="takeprofittrader.com/control-center/pro and the TPT FAQ pages",
    as_of="2026-10-20",
    evaluation=PropPhaseRules(
        id="evaluation",
        has_profit_target=True,
        max_loss_mode="trailing_never_down",
        daily_loss_limit=None,
        min_trading_days=3,
        consistency_share=0.50,
        consistency_measure="profit_target",
        consistency_action="warn",
    ),
    funded=PropPhaseRules(
        id="funded",
        max_loss_mode="trailing_never_down",
        daily_loss_limit=None,
        payout_split=0.80,
        payout_share_of_balance=1.0,
    ),
    sizes=(
        PropAccountSize(id="50k", label="50K", account_size=50_000.0,
                         profit_target=3_000.0, max_loss=2_000.0,
                         min_trading_days=3, max_contracts=6,
                         notes="End-of-day trailing drawdown $2,000; Profit Target "
                               "$3,000; no daily loss limit."),
    ),
    notes="Only the 50K size is encoded because it is the one published on the "
          "firm's own comparison page. TPT has no daily loss limit, and its "
          "consistency rule does not fail the account — it only says you may "
          "not make 50% or more of the profit target in one day. PRO accounts "
          "pay 80/20, day one and daily, with no minimum profitable days.",
)


PROP_FIRMS: dict[str, PropFirmSpec] = {
    spec.id: spec for spec in (TOPSTEP, APEX_EOD, FTMO_PRO, TPT_PRO)
}


def get_spec(firm_id: str) -> PropFirmSpec:
    """Look up a built-in firm spec by id."""
    key = str(firm_id or "").strip().lower().replace(" ", "_").replace("-", "_")
    spec = PROP_FIRMS.get(key)
    if spec is None:
        raise PropFirmError(
            f"unknown prop firm {firm_id!r}",
            detail={"available": sorted(PROP_FIRMS.keys())},
        )
    return spec


def list_firms() -> list[dict[str, Any]]:
    return [spec.to_dict() for spec in PROP_FIRMS.values()]


# ── Trade normalisation ──────────────────────────────────────────────────────

@dataclass
class PropTrade:
    """One closed trade, reduced to what the rules can see."""

    day: str
    pnl: float
    symbol: str = ""
    exit_ts: Optional[str] = None


@dataclass
class TradingDay:
    """One trading day of the log: its realised P&L and its trades in order."""

    day: str
    pnl: float
    trade_pnls: list[float] = field(default_factory=list)

    @property
    def trades(self) -> int:
        return len(self.trade_pnls)


def _trade_pnl(trade: dict[str, Any]) -> Optional[float]:
    for key in ("netPnl", "net_pnl", "pnl", "realizedPnl", "realized_pnl"):
        value = trade.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _trade_timestamp(trade: dict[str, Any]) -> Optional[str]:
    for key in ("exitTs", "exit_ts", "exitTime", "exit_time", "entryTs", "entry_ts",
                "entryTime", "entry_time", "timestamp", "ts", "date"):
        value = trade.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _day_of(timestamp: str, offset_hours: int) -> str:
    """The trading day a timestamp belongs to, given the firm's day offset."""
    from datetime import datetime, timedelta, timezone

    text = str(timestamp).strip()
    normalised = text.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(normalised)
    except ValueError:
        try:
            moment = datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return text[:10]
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    moment = moment.astimezone(timezone.utc) + timedelta(hours=offset_hours)
    return moment.strftime("%Y-%m-%d")


def normalise_trades(trades: list[dict[str, Any]],
                      day_offset_hours: int = 0) -> tuple[list[PropTrade], list[str]]:
    """Reduce a trade log to (trades with a trading day, warnings)."""
    warnings: list[str] = []
    out: list[PropTrade] = []
    for trade in trades or []:
        pnl = _trade_pnl(trade)
        if pnl is None:
            warnings.append("a trade without a recognised P&L field was skipped")
            continue
        timestamp = _trade_timestamp(trade)
        if timestamp is None:
            warnings.append("a trade without a timestamp was skipped")
            continue
        out.append(PropTrade(
            day=_day_of(timestamp, day_offset_hours),
            pnl=pnl,
            symbol=str(trade.get("symbol") or ""),
            exit_ts=timestamp,
        ))
    out.sort(key=lambda t: (t.day, t.exit_ts or ""))
    return out, warnings


def group_by_day(trades: list[PropTrade]) -> list[TradingDay]:
    """Collapse trades into trading days, keeping the chronological order."""
    days: list[TradingDay] = []
    index: dict[str, TradingDay] = {}
    for trade in trades:
        bucket = index.get(trade.day)
        if bucket is None:
            bucket = TradingDay(day=trade.day, pnl=0.0)
            index[trade.day] = bucket
            days.append(bucket)
        bucket.pnl += trade.pnl
        bucket.trade_pnls.append(trade.pnl)
    return days


# ── Path evaluation ──────────────────────────────────────────────────────────

#: The outcomes a path can reach.
OUTCOMES = (
    "passed",
    "failed_max_loss",
    "failed_daily_loss",
    "failed_consistency",
    "failed_access_period",
    "inconclusive_history",
    "inconclusive_no_trades",
)


@dataclass
class PhaseOutcome:
    """What the rules did to one sequence of trading days."""

    status: str
    reason: str = ""
    trading_days: int = 0
    days_simulated: int = 0
    final_balance: float = 0.0
    net_profit: float = 0.0
    profit_target: Optional[float] = None
    effective_target: Optional[float] = None
    best_day: float = 0.0
    worst_day: float = 0.0
    breach_day: Optional[str] = None
    breach_level: Optional[float] = None
    max_loss_threshold: Optional[float] = None
    session_breaks: int = 0
    consistency_violations: list[str] = field(default_factory=list)
    daily_curve: list[dict[str, Any]] = field(default_factory=list)
    payouts: list[dict[str, Any]] = field(default_factory=list)
    total_payout: float = 0.0
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "tradingDays": self.trading_days,
            "daysSimulated": self.days_simulated,
            "finalBalance": round(self.final_balance, 4),
            "netProfit": round(self.net_profit, 4),
            "profitTarget": self.profit_target,
            "effectiveTarget": self.effective_target,
            "bestDay": round(self.best_day, 4),
            "worstDay": round(self.worst_day, 4),
            "breachDay": self.breach_day,
            "breachLevel": self.breach_level,
            "maxLossThreshold": (round(self.max_loss_threshold, 4)
                                 if self.max_loss_threshold is not None else None),
            "sessionBreaks": self.session_breaks,
            "consistencyViolations": list(self.consistency_violations),
            "payouts": self.payouts,
            "totalPayout": round(self.total_payout, 4),
            "dailyCurve": self.daily_curve,
            "warnings": list(self.warnings),
        }


def _initial_threshold(mode: str, balance: float, max_loss: float,
                       ceiling: Optional[float]) -> float:
    if mode == "static_from_start":
        return balance - max_loss
    if mode == "eod_recalculated":
        return balance - max_loss
    return balance - max_loss


def _update_threshold(mode: str, threshold: float, eod_balance: float, balance: float,
                      max_loss: float, ceiling: Optional[float]) -> float:
    """Move the maximum-loss threshold for the next session."""
    if mode == "static_from_start":
        return threshold
    if mode == "eod_recalculated":
        candidate = eod_balance - max_loss
        if ceiling is not None and threshold >= balance + ceiling:
            return balance + ceiling
        if ceiling is not None and candidate >= balance + ceiling:
            return balance + ceiling
        return candidate
    # trailing_never_down: rises with a new end-of-day high, never moves down,
    # and locks once it reaches the starting balance.
    candidate = eod_balance - max_loss
    updated = max(threshold, candidate)
    return min(updated, balance)


def simulate_phase(
    days: list[TradingDay],
    phase: PropPhaseRules,
    size: PropAccountSize,
    *,
    account_size: Optional[float] = None,
    payouts: bool = False,
) -> PhaseOutcome:
    """Apply one phase's rules to a sequence of trading days."""
    start_balance = float(account_size if account_size is not None else size.account_size)
    if phase.profit_target is not None:
        target: Optional[float] = float(phase.profit_target)
    elif phase.has_profit_target:
        target = float(size.profit_target)
    else:
        target = None
    access_period = (phase.max_trading_days if phase.max_trading_days is not None
                     else size.max_trading_days)
    max_loss = phase.max_loss if phase.max_loss > 0 else size.max_loss
    daily_loss = (phase.daily_loss_limit if phase.daily_loss_limit is not None
                  else size.daily_loss_limit)
    min_trading_days = (phase.min_trading_days if phase.min_trading_days > 0
                        else size.min_trading_days)

    outcome = PhaseOutcome(
        status="inconclusive_no_trades",
        reason="no trading days were supplied",
        final_balance=start_balance,
        net_profit=0.0,
        profit_target=target,
        effective_target=target,
    )
    if not days:
        return outcome

    outcome.status = "inconclusive_history"
    balance = start_balance
    threshold = _initial_threshold(phase.max_loss_mode, start_balance, max_loss,
                                   phase.max_loss_ceiling)
    trading_days = 0
    best_day = 0.0
    worst_day = 0.0
    effective_target = float(target) if target is not None else None
    consistency_violations: list[str] = []
    first_day = days[0].day
    profitable_days = 0
    qualifying_days = 0
    payout_balance = 0.0
    payouts_made: list[dict[str, Any]] = []

    for day in days:
        day_start = balance
        breach: Optional[str] = None
        breach_level: Optional[float] = None
        session_break = False

        for pnl in day.trade_pnls:
            balance += pnl
            if balance <= threshold:
                breach = "failed_max_loss"
                breach_level = threshold
                break
            if daily_loss is not None and \
                    (balance - day_start) <= -abs(daily_loss):
                if phase.daily_loss_action == "breach":
                    breach = "failed_daily_loss"
                    breach_level = day_start - abs(daily_loss)
                    break
                session_break = True
                break

        if session_break:
            outcome.session_breaks += 1
        trading_days += 1
        day_pnl = balance - day_start
        best_day = max(best_day, day_pnl)
        worst_day = min(worst_day, day_pnl)
        if day_pnl > 0:
            profitable_days += 1
            if day_pnl >= phase.min_profitable_day_amount:
                qualifying_days += 1

        # Consistency is judged on the end-of-day result. A rule measured against
        # the TOTAL profit is NOT applied here: on the first profitable day the
        # best day is the whole profit, so a mid-flight reading would condemn
        # every trader. That rule is decided at the decision points instead.
        if phase.consistency_share is not None and best_day > 0 \
                and phase.consistency_measure != "total_profit":
            if phase.consistency_measure == "profit_target":
                limit = (phase.consistency_share * effective_target
                         if effective_target is not None else None)
            else:
                limit = None
            if limit is not None and limit > 0 and best_day > limit:
                consistency_violations.append(day.day)
                if phase.consistency_action == "raise_target" and effective_target is not None:
                    raised = best_day / phase.consistency_share
                    if raised > effective_target:
                        effective_target = raised

        threshold = _update_threshold(phase.max_loss_mode, threshold, balance,
                                       start_balance, max_loss,
                                       phase.max_loss_ceiling)

        outcome.daily_curve.append({
            "day": day.day,
            "pnl": round(day_pnl, 4),
            "balance": round(balance, 4),
            "threshold": round(threshold, 4),
            "tradingDays": trading_days,
            "profit": round(balance - start_balance, 4),
        })

        if breach:
            outcome.status = breach
            outcome.reason = _breach_reason(breach, day.day, breach_level)
            outcome.breach_day = day.day
            outcome.breach_level = breach_level
            break

        if phase.has_profit_target and effective_target is not None \
                and trading_days >= min_trading_days \
                and (balance - start_balance) >= effective_target:
            if _consistency_breached(phase, best_day, balance - start_balance,
                                     effective_target):
                outcome.status = "failed_consistency"
                outcome.reason = (
                    f"the consistency rule was violated: the best day carries more "
                    f"than {phase.consistency_share:.0%} of the total profit")
                outcome.breach_day = best_day and days[max(0, trading_days - 1)].day
                break
            outcome.status = "passed"
            outcome.reason = (f"profit target {effective_target:.0f} reached on "
                              f"{day.day} after {trading_days} trading day(s)")
            break

        if access_period is not None:
            span = _calendar_days(first_day, day.day)
            if span > access_period:
                outcome.status = "failed_access_period"
                outcome.reason = (f"the {access_period}-day access period "
                                  f"expired on {day.day} without reaching the target")
                break

        if payouts:
            payout_balance = balance - start_balance
            if phase.payout_frequency_days and trading_days % phase.payout_frequency_days == 0:
                amount = _payout_amount(payout_balance, phase, qualifying_days,
                                         profitable_days)
                if amount:
                    payouts_made.append({
                        "day": day.day, "amount": round(amount, 4),
                        "tradingDays": trading_days,
                    })
                    payout_balance -= amount

    outcome.trading_days = trading_days
    outcome.days_simulated = len(days)
    outcome.final_balance = balance
    outcome.net_profit = balance - start_balance
    outcome.best_day = best_day
    outcome.worst_day = worst_day
    outcome.effective_target = effective_target
    outcome.max_loss_threshold = threshold
    outcome.consistency_violations = consistency_violations

    if outcome.status == "inconclusive_history":
        if _consistency_breached(phase, best_day, balance - start_balance,
                                 effective_target):
            outcome.status = "failed_consistency"
            outcome.reason = (
                f"the consistency rule was violated: the best day carries more "
                f"than {phase.consistency_share:.0%} of the total profit")
        else:
            span = _calendar_days(first_day, days[-1].day)
            if access_period is not None and span < access_period:
                outcome.reason = (
                    f"the log covers {span} calendar day(s) but the access period "
                    f"is {access_period} days; the outcome cannot be decided from "
                    f"this history")
            elif phase.has_profit_target:
                outcome.reason = ("the profit target was not reached within the "
                                  "simulated history")
            else:
                outcome.reason = ("the simulated history ended with the account "
                                  "still active")

    if payouts and outcome.status not in ("failed_max_loss", "failed_daily_loss",
                                          "failed_consistency"):
        amount = _payout_amount(balance - start_balance, phase, qualifying_days,
                                 profitable_days)
        if amount and not payouts_made:
            payouts_made.append({"day": days[-1].day, "amount": round(amount, 4),
                                  "tradingDays": trading_days})
    outcome.payouts = payouts_made
    outcome.total_payout = round(sum(p["amount"] for p in payouts_made), 4)
    return outcome


def _payout_amount(profit_balance: float, phase: PropPhaseRules,
                   qualifying_days: int, profitable_days: int) -> float:
    """The payout available right now, under the phase's payout policy."""
    if profit_balance <= 0:
        return 0.0
    if profitable_days < phase.min_profitable_days:
        return 0.0
    if phase.min_profitable_day_amount > 0 and qualifying_days < phase.min_profitable_days:
        return 0.0
    amount = phase.payout_share_of_balance * profit_balance
    if phase.payout_cap is not None:
        amount = min(amount, phase.payout_cap)
    amount *= phase.payout_split
    if phase.min_payout is not None and amount < phase.min_payout:
        return 0.0
    return amount


def _consistency_breached(phase: PropPhaseRules, best_day: float, total_profit: float,
                          effective_target: Optional[float]) -> bool:
    """Whether the consistency rule is broken at a decision point.

    Only a rule that *breaches* is decided here, and only on the numbers as
    they stand at that moment: a rule measured against the total profit is
    meaningless while the period is still running.
    """
    if phase.consistency_share is None or phase.consistency_action != "breach":
        return False
    if phase.consistency_measure == "profit_target":
        if effective_target is None:
            return False
        limit = phase.consistency_share * effective_target
    else:
        limit = phase.consistency_share * max(0.0, total_profit)
    return limit > 0 and best_day > limit


def _breach_reason(status: str, day: str, level: Optional[float]) -> str:
    if status == "failed_max_loss":
        return (f"the balance reached the maximum-loss threshold ({level:.2f}) on "
                f"{day}")
    if status == "failed_daily_loss":
        return f"the daily loss limit was breached on {day}"
    if status == "failed_consistency":
        return f"the consistency rule was violated on {day}"
    return f"{status} on {day}"


def _calendar_days(first: str, last: str) -> int:
    from datetime import date

    try:
        start = date.fromisoformat(str(first)[:10])
        end = date.fromisoformat(str(last)[:10])
    except ValueError:
        return 0
    return (end - start).days + 1


__all__ = [
    "APEX_EOD",
    "CONSISTENCY_ACTIONS",
    "CONSISTENCY_MEASURES",
    "DAILY_LOSS_ACTIONS",
    "FTMO_PRO",
    "MAX_LOSS_MODES",
    "OUTCOMES",
    "PROP_FIRMS",
    "PhaseOutcome",
    "PropAccountSize",
    "PropFirmError",
    "PropFirmSpec",
    "PropPhaseRules",
    "PropTrade",
    "TPT_PRO",
    "TOPSTEP",
    "TradingDay",
    "get_spec",
    "group_by_day",
    "list_firms",
    "normalise_trades",
    "simulate_phase",
]
