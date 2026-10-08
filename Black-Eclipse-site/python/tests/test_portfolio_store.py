"""Portfolio persistence: idempotency, derived lots, cascade delete, snapshots."""

from __future__ import annotations

from portfolio_helpers import buy, make_portfolio, make_service


def test_transaction_idempotency(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    a = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "10",
                                  "price": "100", "external_id": "imp-1", "source": "import"})
    b = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "10",
                                  "price": "100", "external_id": "imp-1", "source": "import"})
    assert a["status"] == "SUCCESS" and a["duplicate"] is False
    assert b["status"] == "SUCCESS" and b["duplicate"] is True
    assert svc.store.count_transactions(pid) == 1


def test_null_external_ids_are_not_deduplicated(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "1", "100")
    buy(svc, pid, "AAPL", "1", "101")
    assert svc.store.count_transactions(pid) == 2


def test_derived_lots_are_persisted_after_a_trade(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "10", "100")
    lots = svc.store.list_lots(pid, "AAPL")
    assert len(lots) == 1
    from decimal import Decimal

    assert lots[0].quantity == Decimal("10")


def test_delete_portfolio_cascades(tmp_path):
    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    buy(svc, pid, "AAPL", "1", "100")
    assert svc.delete_portfolio(pid) is True
    assert svc.store.get_portfolio(pid) is None
    assert svc.store.count_transactions(pid) == 0
    assert svc.store.list_lots(pid) == []


def test_snapshot_and_audit_are_recorded(tmp_path):
    import asyncio

    svc = make_service(tmp_path)
    pid = make_portfolio(svc)
    svc.add_transaction(pid, {"type": "DEPOSIT", "gross_amount": "1000"})
    buy(svc, pid, "AAPL", "10", "100")
    marks = {"AAPL": {"price": "110", "timestamp": "2026-10-08T00:00:00Z"}}
    out = asyncio.run(svc.snapshot(pid, marks=marks))
    assert out["status"] == "SUCCESS"
    snaps = svc.store.list_snapshots(pid)
    assert len(snaps) == 1
    assert snaps[0]["totalValue"] == "1100.00000000"
    audit = svc.store.list_audit(pid)
    assert any(e["kind"] == "TRANSACTION_RECORDED" for e in audit)
