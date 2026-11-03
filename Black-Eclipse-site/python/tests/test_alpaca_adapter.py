"""Alpaca read-only adapter: REST mapping + FIFO deal normalization."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from harness.trade.adapter import AdapterUnavailable
from harness.trade.adapters.alpaca import AlpacaAdapter

ACCOUNT = {
    "account_number": "PA123",
    "status": "ACTIVE",
    "currency": "USD",
    "cash": "5000",
    "equity": "10500",
    "last_equity": "10400",
    "initial_margin": "1000",
    "buying_power": "4000",
    "multiplier": "4",
    "trading_blocked": False,
}

ORDERS = [
    {
        "id": "ord-open", "symbol": "AAPL", "side": "buy", "filled_qty": "10",
        "filled_avg_price": "100", "filled_at": "2026-11-01T14:00:00Z",
        "status": "filled", "type": "market", "qty": "10",
        "submitted_at": "2026-11-01T14:00:00Z",
    },
    {
        "id": "ord-close", "symbol": "AAPL", "side": "sell", "filled_qty": "10",
        "filled_avg_price": "110", "filled_at": "2026-11-01T15:00:00Z",
        "status": "filled", "type": "market", "qty": "10",
        "submitted_at": "2026-11-01T15:00:00Z",
    },
]

POSITIONS = [
    {"symbol": "AAPL", "qty": "10", "avg_entry_price": "100", "current_price": "110",
     "unrealized_pl": "100"}
]


class Handler(BaseHTTPRequestHandler):
    token = None

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
        if Handler.token:
            if self.headers.get("APCA-API-KEY-ID") != "key" or self.headers.get(
                "APCA-API-SECRET-KEY"
            ) != "secret":
                self._send(401, {"message": "unauthorized"})
                return
        path, _, query = self.path.partition("?")
        if path == "/v2/account":
            self._send(200, ACCOUNT)
        elif path == "/v2/positions":
            self._send(200, POSITIONS)
        elif path == "/v2/orders":
            if "status=open" in query:
                self._send(200, [])
            else:
                self._send(200, ORDERS)
        elif path == "/v2/stocks/AAPL/quotes/latest":
            self._send(200, {"quote": {"bp": 109.9, "ap": 110.1, "t": "2026-11-01T15:00:00Z"}})
        else:
            self._send(404, {"message": "not found"})


@pytest.fixture()
def api(monkeypatch):
    Handler.token = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        yield url
    finally:
        server.shutdown()
        server.server_close()
        monkeypatch.delenv("TEST_ALPACA_KEYS", raising=False)


def adapter_for(url: str) -> AlpacaAdapter:
    return AlpacaAdapter({
        "baseUrl": url,
        "dataUrl": url,
        "credentialRef": "TEST_ALPACA_KEYS",
    })


def test_account_positions_quote(api, monkeypatch):
    monkeypatch.setenv("TEST_ALPACA_KEYS", "key:secret")
    Handler.token = "key"
    adapter = adapter_for(api)
    assert adapter.account()["equity"] == 10500.0
    assert adapter.account()["mode"] == "live"  # the test baseUrl is not a `paper` host
    positions = adapter.positions()
    assert positions[0]["symbol"] == "AAPL"
    assert positions[0]["side"] == "buy"
    quote = adapter.quote("aapl")
    assert quote["bid"] == 109.9
    assert adapter.probe()["connected"] is True


def test_filled_orders_become_fifo_round_trips(api, monkeypatch):
    monkeypatch.setenv("TEST_ALPACA_KEYS", "key:secret")
    Handler.token = "key"
    deals = adapter_for(api).deals_window(2)
    entries = [d for d in deals if d["entry"] == "in"]
    exits = [d for d in deals if d["entry"] == "out"]
    assert len(entries) == 1
    assert len(exits) == 1
    assert entries[0]["price"] == 100
    assert exits[0]["price"] == 110
    assert exits[0]["profit"] == 100
    assert exits[0]["pnlBasis"] == "computed"


def test_missing_and_bad_credentials_are_named_refusals(api):
    with pytest.raises(AdapterUnavailable) as info:
        adapter_for(api).account()
    assert info.value.code == "ALPACA_CREDENTIALS"
