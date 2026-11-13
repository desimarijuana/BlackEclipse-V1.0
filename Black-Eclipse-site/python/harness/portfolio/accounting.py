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
from decimal import Decimal, InvalidOperation
from typing import Optional, Sequence

from .errors import (
    INSUFFICIENT_POSITION,
    INVALID_TRANSACTION,
    LOT_MISMATCH,
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
                    # Deterministic: the same ledger must reproduce the same lot
                    # ids, otherwise a SPECIFIC_ID designation taken from one
                    # `tax_lots` read can never be found on the next recompute.
                    id=f"lot_{tx.id}",
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
                    id=f"lot_{tx.id}",
                )
            )

        elif t in (TransactionType.SPLIT, TransactionType.REVERSE_SPLIT):
            factor = _split_factor(tx)
            if factor and factor > 0:
                for lot in lots:
                    lot.quantity *= factor
                    lot.original_quantity *= factor
                    lot.cost_per_unit = lot.cost_per_unit / factor
                # Quantities are share counts: a split rescales everything held at
                # that instant, so BOTH running quantity rollups must follow the
                # lots. Otherwise the documented invariant
                # `acquired - disposed == remaining` fails after any split (a
                # pre-split disposal would still be counted in old share units).
                result.total_acquired_qty *= factor
                result.total_disposed_qty *= factor
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

    gross = abs(sell.computed_gross())
    # A broker import may carry ONLY a net amount (no price/gross). The cash
    # actually received IS the net amount; falling back to gross (zero) would
    # book a fabricated total loss. Fees/taxes are already inside `net_amount`.
    if sell.net_amount is not None:
        net_proceeds_total = sell.net_amount
    else:
        net_proceeds_total = gross - sell.fees - sell.taxes
    # Proceeds are allocated over the ORIGINAL requested quantity. Dividing the
    # full gross by the clamped quantity after an oversell would inflate the
    # per-unit proceeds (20 requested @300 clamped to 10 available must not
    # report 6000 of proceeds for 10 units).
    requested_qty = abs(sell.quantity)
    proceeds_per_unit = (net_proceeds_total / requested_qty) if requested_qty else ZERO
    # An in-kind transfer/bridge with no stated price moves at BOOK VALUE: the
    # cost basis carries to the destination and no gain/loss is realized.
    book_value = (
        sell.transaction_type in (TransactionType.TRANSFER_OUT, TransactionType.BRIDGE)
        and sell.price is None
    )

    remaining = qty_to_dispose
    for lot, cap in _ordered_lots(lots, method, sell, result):
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
                id=f"match_{sell.id}_{lot.id}",
            )
        )
        result.realized_pnl += realized
        result.realized_cost_basis += cost
        result.total_proceeds += proceeds
        lot.quantity -= take
        remaining -= take
        result.total_disposed_qty += take

    # Drop fully-consumed lots so `open_lots` is set below without dead rows.
    lots[:] = [lot for lot in lots if lot.quantity > 0]


def _ordered_lots(lots: list[TaxLot], method: CostBasisMethod,
                  sell: Transaction, result: AccountingResult) -> list[tuple[TaxLot, Optional[Decimal]]]:
    """Order the open lots for consumption and (for SPECIFIC_ID) cap quantities.

    FIFO: earliest sequence. LIFO: latest sequence. HIFO: highest cost/unit.
    SPECIFIC_ID: the lots named in `sell.lot_selection`, in order, each capped at
    the selected quantity; any unselected lots follow at full quantity so a
    partial selection still fully consumes the disposal.

    A lot designation is a tax instruction, not a hint: an unknown lot id, a
    duplicate selection or a malformed/zero quantity is recorded as an error and
    the whole disposal falls back to plain FIFO (the service's disposal
    pre-check then refuses the write). Silently substituting FIFO for a lot the
    caller named would report a defensible-looking but wrong tax result.
    """
    open_lots = [lot for lot in lots if lot.quantity > 0]
    if method == CostBasisMethod.SPECIFIC_ID and sell.lot_selection:
        by_id = {lot.id: lot for lot in open_lots}
        ordered: list[tuple[TaxLot, Optional[Decimal]]] = []
        chosen: set[str] = set()
        problem = False
        for selection in sell.lot_selection:
            if not isinstance(selection, dict):
                result.errors.append(PortfolioError(
                    INVALID_TRANSACTION,
                    f"{sell.id}: lot_selection entries must be objects with lotId/quantity",
                ))
                problem = True
                continue
            lot_id = selection.get("lotId") or selection.get("lot_id")
            lot = by_id.get(lot_id)
            if lot is None:
                result.errors.append(PortfolioError(
                    LOT_MISMATCH,
                    f"{sell.id}: selected lot {lot_id!r} is not an open lot of {sell.symbol}",
                    {"symbol": sell.symbol, "lotId": lot_id},
                ))
                problem = True
                continue
            if lot.id in chosen:
                result.errors.append(PortfolioError(
                    LOT_MISMATCH,
                    f"{sell.id}: lot {lot.id} is selected more than once",
                    {"symbol": sell.symbol, "lotId": lot.id},
                ))
                problem = True
                continue
            cap = selection.get("quantity")
            try:
                cap_value = Decimal(str(cap)) if cap is not None else lot.quantity
            except (InvalidOperation, ValueError, TypeError):
                result.errors.append(PortfolioError(
                    INVALID_TRANSACTION,
                    f"{sell.id}: lot {lot.id} has a non-numeric selection quantity {cap!r}",
                    {"symbol": sell.symbol, "lotId": lot.id},
                ))
                problem = True
                continue
            if cap_value <= 0:
                result.errors.append(PortfolioError(
                    INVALID_TRANSACTION,
                    f"{sell.id}: lot {lot.id} selection quantity must be positive",
                    {"symbol": sell.symbol, "lotId": lot.id},
                ))
                problem = True
                continue
            ordered.append((lot, cap_value))
            chosen.add(lot.id)
        if problem:
            return [(lot, None) for lot in sorted(open_lots, key=lambda l: l.sequence)]
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
    # Acquisition-date layers exist ONLY to report a meaningful holding period.
    # Basis stays pooled (that is what average cost means); a match's
    # `acquiredAt` is taken from the earliest shares still in the pool, so a
    # position bought three years ago is not mislabeled as a 0-day holding.
    layers: list[list] = []  # [opened_at, quantity]

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
            layers.append([tx.effective_date(), qty])

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
                # Same rule as the lot engine: an imported trade may carry only a
                # net amount, which is the cash actually received (fees/taxes
                # already deducted). Never book gross=0 as a total loss.
                if tx.net_amount is not None:
                    net_total = tx.net_amount
                else:
                    net_total = abs(tx.computed_gross()) - tx.fees - tx.taxes
                requested_qty = abs(tx.quantity)
                net_proceeds = (
                    net_total * qty_to_dispose / requested_qty if requested_qty else ZERO
                )
            realized = net_proceeds - cost
            acquired_at = _consume_average_layers(layers, qty_to_dispose) or tx.effective_date()
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
                    acquired_at=acquired_at,
                    disposed_at=tx.effective_date(),
                    id=f"match_{tx.id}_{AVERAGE_POOL_ID}",
                )
            )
            result.realized_pnl += realized
            result.realized_cost_basis += cost
            result.total_proceeds += net_proceeds
            result.total_disposed_qty += qty_to_dispose
            running_cost -= cost
            running_qty -= qty_to_dispose

        elif t in (TransactionType.SPLIT, TransactionType.REVERSE_SPLIT):
            factor = _split_factor(tx)
            if factor and factor > 0:
                running_qty *= factor
                for layer in layers:
                    layer[1] *= factor
                result.total_acquired_qty *= factor
                result.total_disposed_qty *= factor

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
                opened_at=layers[0][0] if layers else (ordered[0].effective_date() if ordered else ""),
                source_transaction_id=AVERAGE_POOL_ID,
                sequence=0,
                currency=currency,
                id=f"lot_{AVERAGE_POOL_ID}",
            )
        ]


def _consume_average_layers(layers: list[list], qty: Decimal) -> str:
    """Consume acquisition-date layers for holding-period reporting.

    Returns the acquisition date of the earliest shares consumed (or "" when no
    layer can be dated). Basis is NOT taken from these layers — it stays pooled.
    """
    remaining = qty
    acquired_at = ""
    for layer in layers:
        if remaining <= 0:
            break
        take = layer[1] if layer[1] <= remaining else remaining
        if take > 0 and not acquired_at:
            acquired_at = layer[0] or ""
        layer[1] -= take
        remaining -= take
    layers[:] = [layer for layer in layers if layer[1] > 0]
    return acquired_at


def lot_selection_error(tx: Transaction, method: CostBasisMethod) -> Optional[PortfolioError]:
    """Refuse a lot designation the book cannot honour instead of ignoring it."""
    if not tx.lot_selection:
        return None
    if method != CostBasisMethod.SPECIFIC_ID:
        return PortfolioError(
            INVALID_TRANSACTION,
            "lot_selection requires the SPECIFIC_ID cost-basis method "
            f"(this portfolio uses {method.value})",
            {"method": method.value},
        )
    return None


def _split_factor(tx: Transaction) -> Optional[Decimal]:
    """A split transaction encodes its ratio in `quantity` (e.g. 2 = 2:1)."""
    if tx.quantity and tx.quantity > 0:
        return tx.quantity
    return None


__all__ = ["AccountingResult", "compute_accounting", "AVERAGE_POOL_ID"]
