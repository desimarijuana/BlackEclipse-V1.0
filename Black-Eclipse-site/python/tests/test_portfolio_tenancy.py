"""Multi-user tenant enforcement on portfolio reads and mutations."""

from __future__ import annotations

import pytest

from harness.portfolio.errors import PortfolioError
from portfolio_helpers import buy, make_service


def test_owner_is_stamped_on_create(tmp_path):
    svc = make_service(tmp_path)
    pf = svc.create_portfolio("Alice", owner_id="alice")
    assert pf["ownerId"] == "alice"


def test_owner_can_read_and_mutate(tmp_path):
    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Alice", owner_id="alice")["id"]
    out = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "1", "price": "10"},
                              actor_id="alice")
    assert out["status"] == "SUCCESS"


def test_other_user_is_refused_on_read(tmp_path):
    import asyncio

    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Alice", owner_id="alice")["id"]
    with pytest.raises(PortfolioError) as exc:
        asyncio.run(svc.read(pid, actor_id="bob"))
    assert exc.value.code == "PORTFOLIO_FORBIDDEN"


def test_other_user_is_refused_on_mutation(tmp_path):
    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Alice", owner_id="alice")["id"]
    out = svc.add_transaction(pid, {"type": "BUY", "symbol": "AAPL", "quantity": "1", "price": "10"},
                              actor_id="bob")
    assert out["status"] == "FAILED"
    assert out["error"]["code"] == "PORTFOLIO_FORBIDDEN"
    assert svc.store.count_transactions(pid) == 0


def test_delete_by_other_user_is_refused(tmp_path):
    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Alice", owner_id="alice")["id"]
    with pytest.raises(PortfolioError) as exc:
        svc.delete_portfolio(pid, actor_id="bob")
    assert exc.value.code == "PORTFOLIO_FORBIDDEN"
    assert svc.store.get_portfolio(pid) is not None


def test_list_filters_by_owner(tmp_path):
    svc = make_service(tmp_path)
    svc.create_portfolio("Alice", owner_id="alice")
    svc.create_portfolio("Bob", owner_id="bob")
    svc.create_portfolio("Legacy")  # unowned
    alice = {p["name"] for p in svc.list_portfolios(owner_id="alice")}
    assert "Alice" in alice
    assert "Bob" not in alice
    assert all(p["name"] != "Bob" for p in svc.list_portfolios(owner_id="alice"))


def test_unowned_portfolio_is_accessible_locally(tmp_path):
    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Legacy")["id"]
    # No actor asserted (documented single-user local mode) -> allowed.
    assert svc.get_portfolio_record(pid) is not None
    # A random actor is also allowed for an UNOWNED row (nothing to protect).
    assert svc.get_portfolio_record(pid, actor_id="anyone") is not None


def test_agent_tool_forwards_actor(tmp_path):
    import asyncio

    from harness.portfolio.tools import register_portfolio_tools
    from harness.tools import ToolContext, ToolRegistry

    svc = make_service(tmp_path)
    pid = svc.create_portfolio("Alice", owner_id="alice")["id"]
    reg = ToolRegistry()
    register_portfolio_tools(reg)

    async def authorize(tool, args, ctx=None):
        return True

    ctx_alice = ToolContext(run_id="r", log=lambda *_: None, portfolio_service=svc,
                            user_id="alice", authorize_effect=authorize)
    ctx_bob = ToolContext(run_id="r", log=lambda *_: None, portfolio_service=svc,
                          user_id="bob", authorize_effect=authorize)

    ok = asyncio.run(reg.execute("portfolio_add_position", "c1",
                                 {"portfolio_id": pid, "symbol": "AAPL", "quantity": "1", "price": "10"},
                                 ctx_alice))
    assert ok.ok and ok.data["status"] == "SUCCESS"

    denied = asyncio.run(reg.execute("portfolio_add_position", "c2",
                                     {"portfolio_id": pid, "symbol": "MSFT", "quantity": "1", "price": "10"},
                                     ctx_bob))
    # the tool runs (authorized) but the service refuses the cross-tenant write
    assert denied.ok is True
    assert denied.data["status"] == "FAILED"
    assert denied.data["error"]["code"] == "PORTFOLIO_FORBIDDEN"
