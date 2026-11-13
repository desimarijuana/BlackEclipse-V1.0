"""Domain model for the Portfolio Accounting Engine.

The transaction ledger is the source of truth. Positions, cost basis and realized
P&L are DERIVED from the ledger by the accounting engines, never stored as
authoritative state.

Monetary fields are `Decimal` (see `money.py`). Records cross the process
boundary as plain dicts produced by `to_dict()`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from .money import ZERO, money_str, qty_str


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    INTEREST = "INTEREST"
    FEE = "FEE"
    TAX = "TAX"
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    ADJUSTMENT = "ADJUSTMENT"
    # Corporate actions.
    SPIN_OFF = "SPIN_OFF"
    MERGER = "MERGER"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    # A cost-basis-only adjustment (no quantity change), used to reallocate basis
    # across lots (e.g. the parent leg of a spin-off, or a return of capital).
    # Carries `basis_adjustment`.
    COST_BASIS_ADJUSTMENT = "COST_BASIS_ADJUSTMENT"
    # A non-taxable return of capital (reduces basis) — modelled as a basis
    # adjustment with a cash inflow.
    RETURN_OF_CAPITAL = "RETURN_OF_CAPITAL"
    # Subscribe to a rights issue (an acquisition at the subscription price).
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    # Exercise a warrant/option: dispose the warrant, acquire the underlying.
    WARRANT_EXERCISE = "WARRANT_EXERCISE"
    # A realized-P&L-only adjustment (no lots), e.g. the excess of a return of
    # capital over basis. Carries a signed `net_amount`.
    REALIZED_ADJUSTMENT = "REALIZED_ADJUSTMENT"
    # Crypto-oriented. SWAP/BRIDGE move quantity; rewards are acquisitions;
    # STAKE/UNSTAKE change custody only (no lot effect).
    SWAP = "SWAP"
    STAKING_REWARD = "STAKING_REWARD"
    AIRDROP = "AIRDROP"
    BRIDGE = "BRIDGE"
    GAS_FEE = "GAS_FEE"
    STAKE = "STAKE"
    UNSTAKE = "UNSTAKE"
    # A slashing/write-off: the tokens are permanently lost (a disposal at zero
    # proceeds, realizing a loss equal to the consumed basis).
    SLASHING = "SLASHING"
    # A perpetual-futures funding payment; signed `net_amount` (positive = received).
    FUNDING = "FUNDING"


class CostBasisMethod(str, Enum):
    FIFO = "FIFO"
    LIFO = "LIFO"
    AVERAGE_COST = "AVERAGE_COST"
    # Highest-cost lots first (tax-loss harvesting / minimizing gains).
    HIFO = "HIFO"
    # Caller selects exact lots per disposal via the transaction's `lot_selection`.
    SPECIFIC_ID = "SPECIFIC_ID"


# Transaction classes by accounting effect.
ACQUISITIONS = {
    TransactionType.BUY,
    TransactionType.TRANSFER_IN,
    TransactionType.STAKING_REWARD,
    TransactionType.AIRDROP,
    # Corporate-action acquisitions: the service supplies the carried cost basis
    # via `gross_amount` (spin-off child leg, merger acquirer leg).
    TransactionType.SPIN_OFF,
    TransactionType.MERGER,
    TransactionType.RIGHTS_ISSUE,
    TransactionType.WARRANT_EXERCISE,
}
DISPOSALS = {
    TransactionType.SELL,
    TransactionType.TRANSFER_OUT,
    TransactionType.SWAP,
    TransactionType.BRIDGE,
    TransactionType.SLASHING,
}
# Cash-only events (no instrument lot effect).
CASH_IN = {TransactionType.DEPOSIT, TransactionType.DIVIDEND, TransactionType.INTEREST}
CASH_OUT = {TransactionType.WITHDRAWAL, TransactionType.FEE, TransactionType.TAX, TransactionType.GAS_FEE}
# Events that change only the cost basis of open lots (quantity unchanged).
BASIS_ADJUSTING = {TransactionType.COST_BASIS_ADJUSTMENT, TransactionType.RETURN_OF_CAPITAL}
# A realized-P&L-only adjustment (no lots, no basis): carries `net_amount`.
REALIZED_ONLY = {TransactionType.REALIZED_ADJUSTMENT}
# Events that change custody but NOT ownership (staking lock/unlock): audited but
# they never move quantity or basis.
PASSTHROUGH = {TransactionType.STAKE, TransactionType.UNSTAKE, TransactionType.SYMBOL_CHANGE}
# Events that require an instrument.
INSTRUMENT_EVENTS = ACQUISITIONS | DISPOSALS | BASIS_ADJUSTING | REALIZED_ONLY | {
    TransactionType.SPLIT, TransactionType.REVERSE_SPLIT, TransactionType.ADJUSTMENT,
}

# Which transaction kinds the accounting engine can fully process. ADJUSTMENT,
# SWAP and BRIDGE move quantity; BASIS_ADJUSTING reallocates basis.
LOT_AFFECTING = ACQUISITIONS | DISPOSALS | BASIS_ADJUSTING | {
    TransactionType.SPLIT, TransactionType.REVERSE_SPLIT, TransactionType.ADJUSTMENT,
}


class Freshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    VERY_STALE = "VERY_STALE"
    MISSING = "MISSING"


class DataQualityStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


# Freshness thresholds (seconds) applied to a price's own timestamp.
FRESH_MAX_AGE = 15 * 60
STALE_MAX_AGE = 24 * 3600
VERY_STALE_MAX_AGE = 7 * 24 * 3600


@dataclass
class Transaction:
    portfolio_id: str
    transaction_type: TransactionType
    symbol: Optional[str] = None
    quantity: Decimal = ZERO
    price: Optional[Decimal] = None
    fees: Decimal = ZERO
    taxes: Decimal = ZERO
    gross_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    # Cost-basis-only delta for `COST_BASIS_ADJUSTMENT` (no quantity change).
    basis_adjustment: Optional[Decimal] = None
    # SPECIFIC_ID lot selection: [{"lotId": ..., "quantity": ...}, ...].
    lot_selection: Optional[list[dict]] = None
    currency: str = "USD"
    fx_rate: Optional[Decimal] = None
    trade_date: Optional[str] = None
    settlement_date: Optional[str] = None
    timestamp: Optional[str] = None
    account_id: Optional[str] = None
    instrument_id: Optional[str] = None
    asset_type: Optional[str] = None
    external_id: Optional[str] = None
    source: str = "manual"
    notes: Optional[str] = None
    correction_of: Optional[str] = None
    created_by: Optional[str] = None
    id: str = field(default_factory=lambda: new_id("txn"))
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)

    def effective_date(self) -> str:
        return self.trade_date or self.timestamp or self.created_at

    def computed_gross(self) -> Decimal:
        if self.gross_amount is not None:
            return self.gross_amount
        if self.price is not None and self.quantity:
            return self.quantity * self.price
        return ZERO

    def cash_impact(self) -> Decimal:
        """Signed cash change to the account (positive = cash in).

        A transaction may carry an explicit `net_amount` — the cash actually
        settled. When present it already includes fees/taxes, so it must not be
        re-adjusted; ignoring it booked an imported net-only SELL as a pure fee
        outflow and a net-only BUY as a zero-cost trade.
        """
        t = self.transaction_type
        gross = abs(self.computed_gross())
        if t in CASH_IN:
            if self.net_amount is not None:
                return self.net_amount
            return gross - self.taxes - self.fees
        if t in CASH_OUT:
            if self.net_amount is not None:
                return -abs(self.net_amount)
            return -(gross + self.fees + self.taxes)
        if t in (TransactionType.BUY, TransactionType.RIGHTS_ISSUE):
            if self.net_amount is not None:
                return -abs(self.net_amount)
            return -(gross + self.fees + self.taxes)
        if t == TransactionType.SELL:
            if self.net_amount is not None:
                return abs(self.net_amount)
            return gross - self.fees - self.taxes
        if t == TransactionType.RETURN_OF_CAPITAL:
            return (self.net_amount if self.net_amount is not None else gross)
        if t == TransactionType.REALIZED_ADJUSTMENT:
            # Realized-P&L bookkeeping only; any cash is carried by its own event.
            return ZERO
        if t == TransactionType.FUNDING:
            return (self.net_amount if self.net_amount is not None else ZERO)
        if t in (TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT, TransactionType.SLASHING,
                 TransactionType.WARRANT_EXERCISE):
            return ZERO
        return ZERO

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolioId": self.portfolio_id,
            "accountId": self.account_id,
            "instrumentId": self.instrument_id,
            "symbol": self.symbol,
            "assetType": self.asset_type,
            "type": self.transaction_type.value,
            "quantity": qty_str(self.quantity),
            "price": money_str(self.price),
            "grossAmount": money_str(self.computed_gross()),
            "fees": money_str(self.fees),
            "taxes": money_str(self.taxes),
            "netAmount": money_str(self.net_amount),
            "basisAdjustment": money_str(self.basis_adjustment),
            "lotSelection": self.lot_selection,
            "cashImpact": money_str(self.cash_impact()),
            "currency": self.currency,
            "fxRate": money_str(self.fx_rate),
            "tradeDate": self.trade_date,
            "settlementDate": self.settlement_date,
            "timestamp": self.timestamp,
            "externalId": self.external_id,
            "source": self.source,
            "notes": self.notes,
            "correctionOf": self.correction_of,
            "createdBy": self.created_by,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


@dataclass
class TaxLot:
    portfolio_id: str
    symbol: str
    quantity: Decimal
    cost_per_unit: Decimal
    opened_at: str
    source_transaction_id: str
    sequence: int
    original_quantity: Decimal
    fee_allocated: Decimal = ZERO
    currency: str = "USD"
    id: str = field(default_factory=lambda: new_id("lot"))

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.cost_per_unit

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolioId": self.portfolio_id,
            "symbol": self.symbol,
            "quantity": qty_str(self.quantity),
            "originalQuantity": qty_str(self.original_quantity),
            "costPerUnit": money_str(self.cost_per_unit),
            "costBasis": money_str(self.cost_basis),
            "openedAt": self.opened_at,
            "sourceTransactionId": self.source_transaction_id,
            "sequence": self.sequence,
            "currency": self.currency,
        }


@dataclass
class TaxLotMatch:
    portfolio_id: str
    sell_transaction_id: str
    lot_id: str
    symbol: str
    quantity: Decimal
    cost_basis: Decimal
    proceeds: Decimal
    realized_pnl: Decimal
    acquired_at: str
    disposed_at: str
    id: str = field(default_factory=lambda: new_id("match"))

    def holding_days(self) -> int:
        try:
            a = datetime.fromisoformat(self.acquired_at.replace("Z", "+00:00"))
            b = datetime.fromisoformat(self.disposed_at.replace("Z", "+00:00"))
            return max(0, (b - a).days)
        except (ValueError, TypeError):
            # Unknown dates ⇒ unknown term; return -1 so callers do not claim
            # "short-term" or "long-term" when they cannot know.
            return -1

    def to_dict(self) -> dict[str, Any]:
        days = self.holding_days()
        return {
            "id": self.id,
            "portfolioId": self.portfolio_id,
            "sellTransactionId": self.sell_transaction_id,
            "lotId": self.lot_id,
            "symbol": self.symbol,
            "quantity": qty_str(self.quantity),
            "costBasis": money_str(self.cost_basis),
            "proceeds": money_str(self.proceeds),
            "realizedPnl": money_str(self.realized_pnl),
            "acquiredAt": self.acquired_at,
            "disposedAt": self.disposed_at,
            "holdingDays": days if days >= 0 else None,
        }


@dataclass
class Mark:
    """A market price observation with mandatory provenance/freshness."""

    price: Optional[Decimal]
    symbol: str
    currency: str = "USD"
    timestamp: Optional[str] = None
    source: Optional[str] = None
    freshness: Freshness = Freshness.MISSING
    status: DataQualityStatus = DataQualityStatus.UNAVAILABLE
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": money_str(self.price),
            "currency": self.currency,
            "timestamp": self.timestamp,
            "source": self.source,
            "freshness": self.freshness.value,
            "status": self.status.value,
            "warnings": list(self.warnings),
        }


__all__ = [
    "Transaction",
    "TransactionType",
    "TaxLot",
    "TaxLotMatch",
    "Mark",
    "CostBasisMethod",
    "Freshness",
    "DataQualityStatus",
    "ACQUISITIONS",
    "DISPOSALS",
    "CASH_IN",
    "CASH_OUT",
    "BASIS_ADJUSTING",
    "REALIZED_ONLY",
    "PASSTHROUGH",
    "INSTRUMENT_EVENTS",
    "LOT_AFFECTING",
    "new_id",
    "now_iso",
    "FRESH_MAX_AGE",
    "STALE_MAX_AGE",
    "VERY_STALE_MAX_AGE",
]
