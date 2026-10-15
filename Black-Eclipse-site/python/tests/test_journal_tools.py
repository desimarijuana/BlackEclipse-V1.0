"""Journal agent tools: list + approval-gated add against the screen's own store."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness import journal_tools


@pytest.mark.asyncio
async def test_journal_trades_lists(monkeypatch):
    async def fake(method, path, *, body=None):
        assert method == "GET" and path == "/api/journal/trades"
        return 200, {"trades": [{"id": "t1"}, {"id": "t2"}]}

    monkeypatch.setattr(journal_tools, "_journal_request", fake)
    text, data = await journal_tools.journal_trades_handler({}, SimpleNamespace())
    assert data["status"] == "ok" and data["count"] == 2


@pytest.mark.asyncio
async def test_journal_add_trade_verifies_against_the_store(monkeypatch):
    calls = []

    async def fake(method, path, *, body=None):
        calls.append((method, path, body))
        if method == "POST":
            return 200, {"success": True, "trade": {"id": "t9"}}
        return 200, {"trades": [{"id": "t9"}]}

    monkeypatch.setattr(journal_tools, "_journal_request", fake)
    text, data = await journal_tools.journal_add_trade_handler(
        {"symbol": "aapl", "entry": 100, "quantity": 2}, SimpleNamespace()
    )
    assert data["verified"] is True and data["trade"]["id"] == "t9"
    assert calls[0][0] == "POST" and calls[0][2]["symbol"] == "aapl"
    assert calls[1][0] == "GET"  # read back from the store


@pytest.mark.asyncio
async def test_journal_add_trade_rejects_missing_fields(monkeypatch):
    async def fake(method, path, *, body=None):
        raise AssertionError("no request should be made")

    monkeypatch.setattr(journal_tools, "_journal_request", fake)
    _text, data = await journal_tools.journal_add_trade_handler({"symbol": "AAPL"}, SimpleNamespace())
    assert data["status"] == "error"


@pytest.mark.asyncio
async def test_journal_add_trade_unverified_when_not_read_back(monkeypatch):
    async def fake(method, path, *, body=None):
        if method == "POST":
            return 200, {"success": True, "trade": {"id": "t9"}}
        return 200, {"trades": []}

    monkeypatch.setattr(journal_tools, "_journal_request", fake)
    _text, data = await journal_tools.journal_add_trade_handler(
        {"symbol": "AAPL", "entry": 1, "quantity": 1}, SimpleNamespace()
    )
    assert data["status"] == "unverified"


@pytest.mark.asyncio
async def test_journal_add_trade_requires_a_single_use_approval(tmp_path):
    from harness.mcp.approvals import ApprovalStore
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        approvals = ApprovalStore(store)
        authorize = journal_tools.make_journal_authorizer()
        tool = SimpleNamespace(name="journal_add_trade")
        ctx = SimpleNamespace(approvals=approvals, run_id="r", emitter=None, pause_for_approval=False)
        args = {"symbol": "AAPL", "entry": 1, "quantity": 1}

        assert await authorize(tool, args, ctx) is False
        pending = [a for a in approvals.list(status="pending") if a["kind"] == "journal_write"]
        assert len(pending) == 1

        approvals.decide(pending[0]["id"], approve=True, decided_by="test")
        assert await authorize(tool, args, ctx) is True
        assert await authorize(tool, args, ctx) is False  # single-use
    finally:
        store.close()
