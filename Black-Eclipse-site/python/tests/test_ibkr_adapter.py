"""IBKR Client Portal adapter: mapping + FIFO deals against a fake gateway."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.trade.adapter import AdapterUnavailable
from harness.trade.adapters.ibkr import IBKRAdapter

SUMMARY = {
    "currency": "USD",
    "availablefunds": "5000",
    "netliquidation": "10500",
    "initialmargin": "1000",
    "unrealizedpnl": "100",
}

POSITIONS = [
    {"conid": 265598, "contractDesc": "AAPL", "position": "10", "avgCost": "100",
     "mktPrice": "110", "unrealizedPnl": "100"}
]

_NOW = int(time.time() * 1000)
TRADES = [
    {"execution_id": "e1", "symbol": "AAPL", "side": "B", "size": "10", "price": "100",
     "trade_time_r": _NOW - 7_200_000},
    {"execution_id": "e2", "symbol": "AAPL", "side": "S", "size": "10", "price": "110",
     "trade_time_r": _NOW - 3_600_000},
]


class Handler(BaseHTTPRequestHandler):
    cookie = None

    def log_message(self, *args):
        return

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if Handler.cookie and self.headers.get("Cookie") != Handler.cookie:
            self._send(401, {"error": "unauthorized"})
            return
        path, _, query = self.path.partition("?")
        if path == "/iserver/accounts":
            self._send(200, {"accounts": ["DU123"], "selectedAccount": "DU123"})
        elif path == "/portfolio/DU123/summary":
            self._send(200, SUMMARY)
        elif path == "/portfolio/DU123/positions/0":
            self._send(200, POSITIONS)
        elif path == "/iserver/account/orders":
            self._send(200, {"orders": [{"orderId": 1, "ticker": "AAPL", "status": "Submitted"}]})
        elif path == "/iserver/secdef/search":
            self._send(200, [{"conid": 265598, "symbol": "AAPL"}])
        elif path == "/iserver/marketdata/snapshot":
            self._send(200, [{"31": "110", "84": "109.9", "86": "110.1"}])
        elif path == "/iserver/account/trades":
            self._send(200, TRADES)
        else:
            self._send(404, {"error": "not found"})


@pytest.fixture()
def gateway(monkeypatch):
    Handler.cookie = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        monkeypatch.delenv("TEST_IBKR_COOKIE", raising=False)


def adapter_for(url: str) -> IBKRAdapter:
    return IBKRAdapter({
        "baseUrl": url,
        "accountId": "DU123",
        "credentialRef": "TEST_IBKR_COOKIE",
    })


def test_account_positions_orders_quote(gateway, monkeypatch):
    monkeypatch.setenv("TEST_IBKR_COOKIE", "SESSION=abc")
    Handler.cookie = "SESSION=abc"
    adapter = adapter_for(gateway)
    assert adapter.account()["equity"] == 10500.0
    assert adapter.account()["mode"] == "demo"  # DU account
    assert adapter.positions()[0]["symbol"] == "AAPL"
    assert adapter.orders()[0]["ticket"] == 1
    quote = adapter.quote("aapl")
    assert quote["bid"] == 109.9
    assert adapter.probe()["connected"] is True


def test_executions_become_fifo_round_trips(gateway, monkeypatch):
    monkeypatch.setenv("TEST_IBKR_COOKIE", "SESSION=abc")
    Handler.cookie = "SESSION=abc"
    deals = adapter_for(gateway).deals_window(7)
    exits = [d for d in deals if d["entry"] == "out"]
    assert len(exits) == 1
    assert exits[0]["profit"] == 100
    assert exits[0]["pnlBasis"] == "computed"


def test_missing_cookie_is_a_named_refusal(gateway):
    with pytest.raises(AdapterUnavailable) as info:
        adapter_for(gateway).account()
    assert info.value.code == "IBKR_CREDENTIALS"
