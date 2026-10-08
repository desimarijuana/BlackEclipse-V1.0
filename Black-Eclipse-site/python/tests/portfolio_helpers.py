"""Shared helpers for the portfolio test suite."""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from harness.persistence import AgentMemoryStore
from harness.portfolio.service import PortfolioService
from harness.portfolio.store import PortfolioStore


def make_service(tmp_path: Optional[str] = None, method: str = "FIFO") -> PortfolioService:
    base = str(tmp_path) if tmp_path else tempfile.mkdtemp(prefix="be-pf-")
    path = os.path.join(base, "portfolio-test.db")
    store = AgentMemoryStore(path)
    return PortfolioService(PortfolioStore(store))


def make_portfolio(service: PortfolioService, method: str = "FIFO", base: str = "USD") -> str:
    return service.create_portfolio("Test", base_currency=base, cost_basis_method=method)["id"]


def buy(service: PortfolioService, pid: str, symbol: str, qty: str, price: str,
        *, fees: str = "0", date: Optional[str] = None, currency: str = "USD",
        external_id: Optional[str] = None) -> dict:
    payload = {"type": "BUY", "symbol": symbol, "quantity": qty, "price": price,
               "fees": fees, "currency": currency}
    if date:
        payload["trade_date"] = date
    if external_id:
        payload["external_id"] = external_id
    return service.add_transaction(pid, payload)


def sell(service: PortfolioService, pid: str, symbol: str, qty: str, price: str,
         *, fees: str = "0", date: Optional[str] = None) -> dict:
    payload = {"type": "SELL", "symbol": symbol, "quantity": qty, "price": price, "fees": fees}
    if date:
        payload["trade_date"] = date
    return service.add_transaction(pid, payload)
