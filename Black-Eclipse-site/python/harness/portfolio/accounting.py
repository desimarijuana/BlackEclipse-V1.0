"""Tax-lot accounting engines — FIFO, LIFO and weighted average cost.

This is the authoritative accounting core. Given a symbol's chronological
transactions it produces the open tax lots, the lot-by-lot matches for every
disposal, the realized P&L and the remaining position — deterministically.

Invariants upheld (and tested):
  * acquired − disposed == remaining quantity                       (§46)
  * remaining cost basis + realized cost basis == acquisition cost
    (subject to explicitly modelled adjustments)                    (§46)
  * a disposal can never drive a position negative (shorts are not
    supported and are refused, not silently miscalculated)          (§48)

Money and quantity are `Decimal` throughout. No floats touch a balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, Sequence

from .errors import (
    INSUFFICIENT_POSITION,
    SHORT_NOT_SUPPORTED,
    UNSUPPORTED_METHOD,
    UNSUPPORTED_TRANSACTION,
    PortfolioError,
)
from .models import (
    ACQUISITIONS,
    BASIS_ADJUSTING,
    CASH_IN,
    CASH_OUT,
    DISPOSALS,
    PASSTHROUGH,
    REALIZED_ONLY,
    CostBasisMethod,
    TaxLot,
    TaxLotMatch,
    Transaction,
    TransactionType,
)
from .money import ZERO, q_money

AVERAGE_POOL_ID = "average-pool"


@dataclass
class AccountingResult:
    symbol: str
    method: CostBasisMethod
    currency: str = "USD"
    open_lots: list[TaxLot] = field(default_factory=list)
    matches: list[TaxLotMatch] = field(default_factory=list)
    realized_pnl: Decimal = ZERO
    realized_cost_basis: Decimal = ZERO
    total_proceeds: Decimal = ZERO
    total_acquired_qty: Decimal = ZERO
    total_disposed_qty: Decimal = ZERO
    total_basis_adjustments: Decimal = ZERO
    warnings: list[str] = field(default_factory=list)
    errors: list[PortfolioError] = field(default_factory=list)

    @property
    def remaining_qty(self) -> Decimal:
        total = ZERO
        for lot in self.open_lots:
            total += lot.quantity
        return total

    @property
    def remaining_cost_basis(self) -> Decimal:
        total = ZERO
        for lot in self.open_lots:
            total += lot.cost_basis
        return total

    @property
    def average_cost(self) -> Optional[Decimal]:
        qty = self.remaining_qty
        if qty == 0:
            return None
        return self.remaining_cost_basis / qty

    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "method": self.method.value,
            "currency": self.currency,
            "remainingQuantity": str(self.remaining_qty),
            "remainingCostBasis": str(q_money(self.remaining_cost_basis)),
            "averageCost": str(q_money(self.average_cost)) if self.average_cost is not None else None,
            "realizedPnl": str(q_money(self.realized_pnl)),
            "realizedCostBasis": str(q_money(self.realized_cost_basis)),
            "totalProceeds": str(q_money(self.total_proceeds)),
            "totalAcquiredQuantity": str(self.total_acquired_qty),
            "totalDisposedQuantity": str(self.total_disposed_qty),
            "totalBasisAdjustments": str(q_money(self.total_basis_adjustments)),
            "openLots": [lot.to_dict() for lot in self.open_lots],
            "matches": [m.to_dict() for m in self.matches],
            "warnings": list(self.warnings),
            "errors": [e.to_dict() for e in self.errors],
        }


def _sort_key(tx: Transaction) -> tuple:
    # Order by effective date then creation timestamp. The sort is STABLE, so
    # transactions with identical timestamps keep their input (ledger/insertion)
    # order — never a random id tiebreak, which could sort a SELL before the BUY
    # that funds it when two rows share a millisecond.
    return (tx.effective_date() or "", tx.created_at)


def _chronological(transactions: Sequence[Transaction]) -> list[Transaction]:
    return sorted(transactions, key=_sort_key)


def compute_accounting(
    portfolio_id: str,
    symbol: str,
    transactions: Sequence[Transaction],
    method: CostBasisMethod,
    *,
    currency: str = "USD",
) -> AccountingResult:
    """Compute lots, matches and realized P&L for ONE symbol.

    Cash-only transactions (deposits/withdrawals/dividends/fees/taxes) are
    ignored here — they belong to the cash ledger, not instrument accounting.
    """
    result = AccountingResult(symbol=symbol, method=method, currency=currency)
    ordered = _chronological(transactions)

    if method == CostBasisMethod.AVERAGE_COST:
        _run_average_cost(portfolio_id, symbol, ordered, currency, result)
    elif method in (CostBasisMethod.FIFO, CostBasisMethod.LIFO,
                    CostBasisMethod.HIFO, CostBasisMethod.SPECIFIC_ID):
        _run_lot_method(portfolio_id, symbol, ordered, method, currency, result)
    else:  # pragma: no cover - CostBasisMethod is closed
        raise PortfolioError(
            UNSUPPORTED_METHOD, f"unknown cost-basis method {method!r}", {"method": str(method)}
        )

    result.total_disposed_qty = sum((m.quantity for m in result.matches), ZERO)
    return result


# ── FIFO / LIFO ───────────────────────────────────────────────────────────────

def _run_lot_method(
    portfolio_id: str,
    symbol: str,
    ordered: Sequence[Transaction],
    method: CostBasisMethod,
    currency: str,
    result: AccountingResult,
) -> None:
    lots: list[TaxLot] = []
    seq = 0

    for tx in ordered:
        t = tx.transaction_type

        if t in ACQUISITIONS:
            seq += 1
            cost = _acquisition_cost_per_unit(tx)
            if cost is None:
                cost = ZERO
                result.warnings.append(
                    f"{t.value} {tx.id} has no price/cost basis for {symbol}; "
                    "lot recorded at zero basis"
                )
            qty = abs(tx.quantity)
            if qty == 0:
                continue
            result.total_acquired_qty += qty
            lots.append(
                TaxLot(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    quantity=qty,
                    original_quantity=qty,
                    cost_per_unit=cost,
                    fee_allocated=tx.fees,
                    opened_at=tx.effective_date(),
                    source_transaction_id=tx.id,
                    sequence=seq,
                    currency=currency,
                )
            )

        elif t in DISPOSALS or (t == TransactionType.ADJUSTMENT and tx.quantity < 0):
            qty_to_dispose = abs(tx.quantity)
            if qty_to_dispose == 0:
                continue
            _consume_lots(portfolio_id, symbol, tx, qty_to_dispose, lots, method, result)

        elif t == TransactionType.ADJUSTMENT:  # positive adjustment = acquisition
            seq += 1
            qty = abs(tx.quantity)
            cost = _acquisition_cost_per_unit(tx) or ZERO
            if qty == 0:
                continue
            result.total_acquired_qty += qty
            lots.append(
                TaxLot(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    quantity=qty,
                    original_quantity=qty,
                    cost_per_unit=cost,
                    opened_at=tx.effective_date(),
                    source_transaction_id=tx.id,
                    sequence=seq,
                    currency=currency,
                    fee_allocated=tx.fees,
                )
            )

        elif t in (TransactionType.SPLIT, TransactionType.REVERSE_SPLIT):
            factor = _split_factor(tx)
            if factor and factor > 0:
                for lot in lots:
                    lot.quantity *= factor
                    lot.original_quantity *= factor
                    lot.cost_per_unit = lot.cost_per_unit / factor
            else:
                result.warnings.append(f"{t.value} {tx.id} ignored: no valid split ratio")

        elif t in BASIS_ADJUSTING:
            _apply_basis_adjustment(tx, lots, result)

        elif t in REALIZED_ONLY:
            result.realized_pnl += _realized_amount(tx)

        elif t in PASSTHROUGH or t == TransactionType.FUNDING:
            continue  # custody/bookkeeping only — never changes quantity or basis

        elif t in CASH_IN or t in CASH_OUT:
            continue  # handled by the cash ledger

        else:
            result.warnings.append(f"transaction type {t.value} ignored by lot accounting")

    result.open_lots = [lot for lot in lots if lot.quantity > 0]


def _acquisition_cost_per_unit(tx: Transaction) -> Optional[Decimal]:
    qty = abs(tx.quantity)
    if qty == 0:
        return None
    if tx.price is not None:
        return (qty * tx.price + tx.fees) / qty
    if tx.gross_amount is not None:
        return (abs(tx.gross_amount) + tx.fees) / qty
    if tx.net_amount is not None:
        return abs(tx.net_amount) / qty
    return None


def _consume_lots(
    portfolio_id: str,
    symbol: str,
    sell: Transaction,
    qty_to_dispose: Decimal,
    lots: list[TaxLot],
    method: CostBasisMethod,
    result: AccountingResult,
) -> None:
    available = sum((lot.quantity for lot in lots), ZERO)
    if qty_to_dispose > available:
        result.errors.append(
            PortfolioError(
                SHORT_NOT_SUPPORTED if available == 0 else INSUFFICIENT_POSITION,
                f"cannot dispose {qty_to_dispose} of {symbol}: only {available} available "
                "(short positions are not supported)",
                {"symbol": symbol, "requested": str(qty_to_dispose), "available": str(available)},
            )
        )
        qty_to_dispose = available
        if qty_to_dispose == 0:
            return

    gross = sell.computed_gross()
    net_proceeds = gross - sell.fees - sell.taxes
    # Proceeds allocated per disposed unit (net of fees/taxes).
    proceeds_per_unit = (net_proceeds / qty_to_dispose) if qty_to_dispose else ZERO
    # An in-kind transfer/bridge with no stated price moves at BOOK VALUE: the
    # cost basis carries to the destination and no gain/loss is realized.
    book_value = (
        sell.transaction_type in (TransactionType.TRANSFER_OUT, TransactionType.BRIDGE)
        and sell.price is None
    )

    remaining = qty_to_dispose
    for lot, cap in _ordered_lots(lots, method, sell):
        if remaining <= 0:
            break
        if lot.quantity <= 0:
            continue
        available = lot.quantity if cap is None or cap > lot.quantity else cap
        if available <= 0:
            continue
        take = available if available <= remaining else remaining
        cost = take * lot.cost_per_unit
        proceeds = cost if book_value else proceeds_per_unit * take
        realized = proceeds - cost
        result.matches.append(
            TaxLotMatch(
                portfolio_id=portfolio_id,
                sell_transaction_id=sell.id,
                lot_id=lot.id,
                symbol=symbol,
                quantity=take,
                cost_basis=q_money(cost),
                proceeds=q_money(proceeds),
                realized_pnl=q_money(realized),
                acquired_at=lot.opened_at,
                disposed_at=sell.effective_date(),
            )
        )
        result.realized_pnl += realized
        result.realized_cost_basis += cost
        result.total_proceeds += proceeds
        lot.quantity -= take
        remaining -= take

    # Drop fully-consumed lots so `open_lots` is set below without dead rows.
    lots[:] = [lot for lot in lots if lot.quantity > 0]


def _ordered_lots(lots: list[TaxLot], method: CostBasisMethod,
                  sell: Transaction) -> list[tuple[TaxLot, Optional[Decimal]]]:
    """Order the open lots for consumption and (for SPECIFIC_ID) cap quantities.

    FIFO: earliest sequence. LIFO: latest sequence. HIFO: highest cost/unit.
    SPECIFIC_ID: the lots named in `sell.lot_selection`, in order, each capped at
    the selected quantity; any unselected lots follow at full quantity so a
    partial selection still fully consumes the disposal.
    """
    open_lots = [lot for lot in lots if lot.quantity > 0]
    if method == CostBasisMethod.SPECIFIC_ID and sell.lot_selection:
        by_id = {lot.id: lot for lot in open_lots}
        ordered: list[tuple[TaxLot, Optional[Decimal]]] = []
        chosen: set[str] = set()
        for selection in sell.lot_selection:
            lot_id = selection.get("lotId") or selection.get("lot_id")
            lot = by_id.get(lot_id)
            if lot is None or lot.id in chosen:
                continue
            cap = selection.get("quantity")
            ordered.append((lot, Decimal(str(cap)) if cap is not None else lot.quantity))
            chosen.add(lot.id)
        ordered.extend((lot, None) for lot in open_lots if lot.id not in chosen)
        return ordered
    if method == CostBasisMethod.HIFO:
        return [(lot, None) for lot in sorted(open_lots, key=lambda l: l.cost_per_unit, reverse=True)]
    if method == CostBasisMethod.LIFO:
        return [(lot, None) for lot in sorted(open_lots, key=lambda l: l.sequence, reverse=True)]
    return [(lot, None) for lot in sorted(open_lots, key=lambda l: l.sequence)]


def _realized_amount(tx: Transaction) -> Decimal:
    if tx.net_amount is not None:
        return tx.net_amount
    return tx.computed_gross()


def _apply_basis_adjustment(tx: Transaction, lots: list[TaxLot], result: AccountingResult) -> None:
    """Reallocate cost basis across the OPEN lots without changing quantity.

    Every open lot's per-unit cost is scaled by (B + Δ)/B, so the total basis
    becomes B + Δ while each lot keeps its relative basis. Used for the parent
    leg of a spin-off. Clamped at zero (never a negative basis).
    """
    delta = tx.basis_adjustment
    if delta is None:
        result.warnings.append(f"{tx.id}: COST_BASIS_ADJUSTMENT without basis_adjustment ignored")
        return
    open_lots = [lot for lot in lots if lot.quantity > 0]
    total = sum((lot.quantity * lot.cost_per_unit for lot in open_lots), ZERO)
    if total <= 0:
        result.warnings.append(f"{tx.id}: basis adjustment with no open lots ignored")
        return
    new_total = total + delta
    if new_total < 0:
        result.warnings.append(f"{tx.id}: basis adjustment clamped (would make basis negative)")
        new_total = ZERO
    factor = new_total / total
    for lot in open_lots:
        lot.cost_per_unit = lot.cost_per_unit * factor
    result.total_basis_adjustments += (new_total - total)


# ── Average cost ──────────────────────────────────────────────────────────────

def _run_average_cost(
    portfolio_id: str,
    symbol: str,
    ordered: Sequence[Transaction],
    currency: str,
    result: AccountingResult,
) -> None:
    running_qty = ZERO
    running_cost = ZERO
    seq = 0

    for tx in ordered:
        t = tx.transaction_type

        if t in ACQUISITIONS or (t == TransactionType.ADJUSTMENT and tx.quantity > 0):
            seq += 1
            qty = abs(tx.quantity)
            if qty == 0:
                continue
            cost = _acquisition_cost_per_unit(tx)
            if cost is None:
                result.warnings.append(
                    f"{t.value} {tx.id} has no price/cost basis for {symbol}; recorded at zero basis"
                )
                cost = ZERO
            running_qty += qty
            running_cost += cost * qty
            result.total_acquired_qty += qty

        elif t in DISPOSALS or (t == TransactionType.ADJUSTMENT and tx.quantity < 0):
            qty_to_dispose = abs(tx.quantity)
            if qty_to_dispose == 0:
                continue
            if running_qty <= 0:
                result.errors.append(
                    PortfolioError(
                        SHORT_NOT_SUPPORTED,
                        f"cannot dispose {qty_to_dispose} of {symbol}: no position "
                        "(short positions are not supported)",
                        {"symbol": symbol},
                    )
                )
                continue
            if qty_to_dispose > running_qty:
                result.errors.append(
                    PortfolioError(
                        INSUFFICIENT_POSITION,
                        f"cannot dispose {qty_to_dispose} of {symbol}: only {running_qty} available",
                        {"symbol": symbol, "requested": str(qty_to_dispose), "available": str(running_qty)},
                    )
                )
                qty_to_dispose = running_qty
            avg = running_cost / running_qty
            cost = avg * qty_to_dispose
            book_value = (
                tx.transaction_type in (TransactionType.TRANSFER_OUT, TransactionType.BRIDGE)
                and tx.price is None
            )
            if book_value:
                net_proceeds = cost
            else:
                gross = tx.computed_gross()
                net_proceeds_total = gross - tx.fees - tx.taxes
                net_proceeds = (net_proceeds_total / abs(tx.quantity)) * qty_to_dispose if tx.quantity else ZERO
            realized = net_proceeds - cost
            result.matches.append(
                TaxLotMatch(
                    portfolio_id=portfolio_id,
                    sell_transaction_id=tx.id,
                    lot_id=AVERAGE_POOL_ID,
                    symbol=symbol,
                    quantity=qty_to_dispose,
                    cost_basis=q_money(cost),
                    proceeds=q_money(net_proceeds),
                    realized_pnl=q_money(realized),
                    acquired_at=tx.effective_date(),
                    disposed_at=tx.effective_date(),
                )
            )
            result.realized_pnl += realized
            result.realized_cost_basis += cost
            result.total_proceeds += net_proceeds
            running_cost -= cost
            running_qty -= qty_to_dispose

        elif t in (TransactionType.SPLIT, TransactionType.REVERSE_SPLIT):
            factor = _split_factor(tx)
            if factor and factor > 0:
                running_qty *= factor

        elif t in BASIS_ADJUSTING:
            delta = tx.basis_adjustment or ZERO
            new_cost = running_cost + delta
            if new_cost < 0:
                result.warnings.append(f"{tx.id}: basis adjustment clamped (would make basis negative)")
                new_cost = ZERO
            result.total_basis_adjustments += (new_cost - running_cost)
            running_cost = new_cost

        elif t in REALIZED_ONLY:
            result.realized_pnl += _realized_amount(tx)

        elif t in PASSTHROUGH or t == TransactionType.FUNDING:
            continue

        elif t in CASH_IN or t in CASH_OUT:
            continue

    if running_qty > 0:
        avg_cost = running_cost / running_qty
        result.open_lots = [
            TaxLot(
                portfolio_id=portfolio_id,
                symbol=symbol,
                quantity=running_qty,
                original_quantity=running_qty,
                cost_per_unit=avg_cost,
                opened_at=ordered[0].effective_date() if ordered else "",
                source_transaction_id=AVERAGE_POOL_ID,
                sequence=0,
                currency=currency,
            )
        ]


def _split_factor(tx: Transaction) -> Optional[Decimal]:
    """A split transaction encodes its ratio in `quantity` (e.g. 2 = 2:1)."""
    if tx.quantity and tx.quantity > 0:
        return tx.quantity
    return None


__all__ = ["AccountingResult", "compute_accounting", "AVERAGE_POOL_ID"]
