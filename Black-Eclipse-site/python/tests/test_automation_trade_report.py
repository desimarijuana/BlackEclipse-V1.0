"""An unattended bot must report the ORDER it proposed, with its real window.

A trade approval expires quickly on purpose (a stale market order is worse than
none), so a scheduled run that says "Finished as asked" while an order sits
unapproved is misleading. The report names the order, the approval id, and how
long the operator actually has. These are the rules the delivery contract asserts.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from harness.automation.delivery import deliver_automation, render_run_report
from harness.automation.dispatcher import Dispatcher


def _definition(*, adapter: str = "in_app") -> SimpleNamespace:
    return SimpleNamespace(
        id="bot_1",
        name="Pre-open trade finder",
        version=3,
        delivery=SimpleNamespace(
            wants=lambda state: True,
            effective_targets=lambda: [SimpleNamespace(adapter=adapter, destination=None)],
        ),
    )


def _iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat().replace(
        "+00:00", "Z"
    )


def _pending(seconds: int = 300, summary: str = "BUY 0.10 EURUSD market · SL 1.0800") -> dict:
    return {
        "approvalId": "appr_abc123",
        "summary": summary,
        "expiresAt": _iso(seconds),
        "risk": "high",
    }


def test_a_pending_order_is_the_first_line_and_names_the_window():
    report = render_run_report(
        _definition(), "completed", "Two setups met the bar.", pending_approvals=[_pending(300)]
    )
    first = report.splitlines()[0]
    assert first.startswith("AWAITING APPROVAL — BUY 0.10 EURUSD market")
    # The window floors on purpose (a few milliseconds elapse between building
    # the fixture and rendering), so accept 4 or 5 for a five-minute TTL.
    assert re.search(r"good for [45] minutes", first), first
    # The id is present so the operator (and the composer banner) can act on it.
    assert "appr_abc123" in report
    # The model's own findings are not lost.
    assert "Two setups met the bar." in report


def test_a_short_window_is_reported_in_seconds():
    report = render_run_report(_definition(), "completed", None, pending_approvals=[_pending(45)])
    # The window is recomputed from the live clock, so crossing a second boundary
    # between building the fixture and rendering legitimately shaves one: this is
    # the same floor the minutes case above allows for.
    match = re.search(r"good for (\d+) seconds", report.splitlines()[0])
    assert match, report.splitlines()[0]
    assert 43 <= int(match.group(1)) <= 45


def test_an_expired_window_says_so_instead_of_implying_it_still_works():
    report = render_run_report(_definition(), "completed", None, pending_approvals=[_pending(-60)])
    assert "window has already closed" in report.splitlines()[0]


def test_a_missing_expiry_still_warns_that_it_is_short_lived():
    pending = _pending()
    pending.pop("expiresAt")
    report = render_run_report(_definition(), "completed", None, pending_approvals=[pending])
    assert "expires quickly" in report.splitlines()[0]


def test_multiple_pending_orders_are_each_named():
    report = render_run_report(
        _definition(), "completed", None,
        pending_approvals=[_pending(summary="BUY 0.10 EURUSD"), _pending(summary="SELL 0.05 GBPUSD")],
    )
    assert "BUY 0.10 EURUSD" in report
    assert "SELL 0.05 GBPUSD" in report


def test_no_pending_order_keeps_the_plain_outcome_contract():
    report = render_run_report(_definition(), "completed", None)
    assert report.splitlines()[0] == "Finished as asked."
    assert "produced no result" in report


def test_a_completed_run_with_a_pending_order_is_not_reported_as_empty():
    report = render_run_report(
        _definition(), "completed", None, pending_approvals=[_pending()]
    )
    assert "produced no result" not in report


def test_delivery_carries_the_bot_and_the_approval_ids():
    published: list[dict] = []
    bus = SimpleNamespace(publish=lambda event: published.append(event) or True)
    store = SimpleNamespace(record_delivery=lambda *a, **k: None)
    asyncio.run(deliver_automation(
        _definition(), execution_id="ex_1", run_id="run_1", state="completed",
        output="done", store=store, bus=bus, pending_approvals=[_pending()],
    ))
    data = published[0]["data"]
    assert data["botId"] == "bot_1"
    assert data["approvalIds"] == ["appr_abc123"]


def test_artifact_report_carries_the_pending_order(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "harness.automation.delivery.artifact_dir_for", lambda run_id: tmp_path / run_id
    )
    store = SimpleNamespace(record_delivery=lambda *a, **k: None)
    asyncio.run(deliver_automation(
        _definition(adapter="artifact"), execution_id="ex_1", run_id="run_1",
        state="completed", output="done", store=store, bus=None,
        pending_approvals=[_pending()],
    ))
    report = (tmp_path / "run_1" / "report.md").read_text(encoding="utf-8")
    assert report.startswith("AWAITING APPROVAL")


class _Brokers:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def list_approvals(self, status: str | None = None, limit: int = 50):
        return [row for row in self._rows if status is None or row["status"] == status]


def test_the_dispatcher_reports_only_this_runs_pending_orders():
    rows = [
        {"id": "appr_mine", "status": "pending", "requestedByRunId": "run_1",
         "actionSummary": "BUY 0.1 EURUSD", "expiresAt": _iso(120), "risk": "high"},
        {"id": "appr_other", "status": "pending", "requestedByRunId": "run_2",
         "actionSummary": "SELL 0.1 GBPUSD", "expiresAt": _iso(120), "risk": "high"},
        {"id": "appr_done", "status": "approved", "requestedByRunId": "run_1",
         "actionSummary": "BUY 0.1 EURUSD", "expiresAt": _iso(120), "risk": "high"},
    ]
    dispatcher = Dispatcher(SimpleNamespace(brokers=_Brokers(rows)))
    pending = dispatcher._pending_trade_approvals("run_1")
    assert [p["approvalId"] for p in pending] == ["appr_mine"]
    assert pending[0]["summary"] == "BUY 0.1 EURUSD"


def test_the_dispatcher_tolerates_a_missing_broker_layer():
    dispatcher = Dispatcher(SimpleNamespace(brokers=None))
    assert dispatcher._pending_trade_approvals("run_1") == []


def test_the_dispatcher_tolerates_a_broken_approval_store():
    class Broken:
        def list_approvals(self, status=None, limit=50):
            raise RuntimeError("db gone")

    dispatcher = Dispatcher(SimpleNamespace(brokers=Broken()))
    assert dispatcher._pending_trade_approvals("run_1") == []
