"""Corporate actions: split, spin-off, merger, symbol change, basis adjustments."""

from __future__ import annotations

from decimal import Decimal

from portfolio_helpers import buy, make_portfolio, make_service


def _lots(svc, pid):
    out = svc.calculate_tax_lots(pid, persist=True)
    return {s["symbol"]: s for s in out["symbols"]}


def test_split_via_corporate_action(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "X", "10", "100")
    out = svc.apply_corporate_action(pid, {"action": "SPLIT", "symbol": "X", "ratio": "2"})
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["X"]["remainingQuantity"]) == Decimal("20")
    assert Decimal(lots["X"]["remainingCostBasis"]) == Decimal("1000")


def test_spin_off_reallocates_basis(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "PAR", "10", "100")  # basis 1000
    out = svc.apply_corporate_action(pid, {
        "action": "SPIN_OFF", "parent_symbol": "PAR", "child_symbol": "CHI",
        "child_quantity": "5", "child_price": "40", "parent_price": "120",
    })
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    # child fmv 200, parent fmv 1200 => child gets 200/1400 of 1000 = 142.857...
    child_basis = Decimal(lots["CHI"]["remainingCostBasis"])
    parent_basis = Decimal(lots["PAR"]["remainingCostBasis"])
    assert Decimal(lots["CHI"]["remainingQuantity"]) == Decimal("5")
    assert abs(child_basis - Decimal("142.85714286")) < Decimal("0.01")
    # basis is conserved: parent + child == original
    assert abs((child_basis + parent_basis) - Decimal("1000")) < Decimal("0.01")


def test_merger_all_stock_carries_basis(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "A", "10", "100")  # basis 1000
    out = svc.apply_corporate_action(pid, {
        "action": "MERGER", "acquired_symbol": "A", "acquirer_symbol": "B",
        "exchange_ratio": "0.5", "acquirer_price": "220",
    })
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["A"]["remainingQuantity"]) == Decimal("0")
    assert Decimal(lots["B"]["remainingQuantity"]) == Decimal("5")
    assert Decimal(lots["B"]["remainingCostBasis"]) == Decimal("1000")


def test_merger_with_cash_consideration(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "5000"})
    buy(svc, pid, "A", "10", "100")
    out = svc.apply_corporate_action(pid, {
        "action": "MERGER", "acquired_symbol": "A", "acquirer_symbol": "B",
        "exchange_ratio": "0.5", "acquirer_price": "200", "cash_per_share": "10",
    })
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["A"]["remainingQuantity"]) == Decimal("0")
    assert Decimal(lots["B"]["remainingQuantity"]) == Decimal("5")
    # carried basis < 1000 because the cash boot removed some basis
    assert Decimal(lots["B"]["remainingCostBasis"]) < Decimal("1000")


def test_symbol_change_moves_position(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "OLD", "10", "100")
    out = svc.apply_corporate_action(pid, {
        "action": "SYMBOL_CHANGE", "old_symbol": "OLD", "new_symbol": "NEW",
    })
    assert out["status"] == "SUCCESS"
    lots = _lots(svc, pid)
    assert Decimal(lots["OLD"]["remainingQuantity"]) == Decimal("0")
    assert Decimal(lots["NEW"]["remainingQuantity"]) == Decimal("10")
    assert Decimal(lots["NEW"]["remainingCostBasis"]) == Decimal("1000")
    audit = svc.store.list_audit(pid)
    assert any(e["kind"] == "CORPORATE_ACTION" for e in audit)


def test_unsupported_corporate_action_is_refused(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    out = svc.apply_corporate_action(pid, {"action": "BUYBACK"})
    assert out["status"] == "FAILED"
    assert out["error"]["code"] == "UNSUPPORTED_CORPORATE_ACTION"


def test_spin_off_without_fmv_is_refused(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "PAR", "10", "100")
    out = svc.apply_corporate_action(pid, {
        "action": "SPIN_OFF", "parent_symbol": "PAR", "child_symbol": "CHI", "child_quantity": "5",
    })
    assert out["status"] == "FAILED"
    assert out["error"]["code"] == "INVALID_PRICE"
