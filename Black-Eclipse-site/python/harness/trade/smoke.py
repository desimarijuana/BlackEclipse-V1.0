"""One-command broker smoke test.

Runs the same read paths the UI uses, then one reconciliation pass, and reports
what actually answered. It is read-only against the broker: the only write is
the mirror (`BrokerFill`/`BrokerPositionSnapshot`/`BrokerSyncState`), exactly
like a normal sync. Any failure is reported as a failed check, never hidden.
"""

from __future__ import annotations

import time
from typing import Any

from .adapter import AdapterUnavailable, BrokerAdapter
from .registry import make_adapter


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def run_smoke(service: Any, connection_id: str, days: int = 7) -> dict[str, Any]:
    connection = service.connections.get(connection_id)
    if connection is None:
        raise KeyError(f"no broker connection {connection_id!r}")
    safe_days = max(1, min(int(days or 7), 90))
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "ok": False,
        "connectionId": connection_id,
        "kind": connection.kind,
        "mode": connection.mode.value,
        "days": safe_days,
        "checks": checks,
        "account": None,
        "counts": {},
        "sync": None,
    }

    probe_result = service.test_connection(connection_id)
    probe = probe_result.get("probe") or {}
    connected = bool(probe.get("connected"))
    checks.append(
        _check(
            "probe",
            connected,
            "connected" if connected else str(probe.get("reason") or probe.get("code") or "no answer"),
        )
    )
    if not connected:
        report["error"] = str(probe.get("reason") or "the broker did not answer")
        return report

    adapter: BrokerAdapter | None = None
    try:
        adapter = make_adapter(connection.kind, connection.config)
        account = adapter.account()
        checks.append(_check("account", bool(account), f"equity {account.get('equity')}"))
        report["account"] = account

        positions = adapter.positions()
        checks.append(_check("positions", True, f"{len(positions)} open"))

        orders = adapter.orders()
        checks.append(_check("orders", True, f"{len(orders)} working"))

        started = int(time.time() * 1000)
        deals = adapter.deals_window(safe_days)
        checks.append(
            _check("deals", True, f"{len(deals)} deal leg(s) in {safe_days}d")
        )
        report["counts"] = {
            "positions": len(positions),
            "orders": len(orders),
            "deals": len(deals),
            "dealWindowMs": int(time.time() * 1000) - started,
        }
    except AdapterUnavailable as exc:
        checks.append(_check("read", False, f"{exc.code}: {exc.reason}"))
        report["error"] = exc.reason
        return report
    except Exception as exc:  # noqa: BLE001 - a smoke test must report, not crash
        checks.append(_check("read", False, str(exc)))
        report["error"] = str(exc)
        return report
    finally:
        try:
            if adapter is not None:
                adapter.close()
        except Exception:  # noqa: BLE001
            pass

    # The write path: this is the same reconciliation the UI/scheduler uses.
    sync = service.sync_connection(connection_id, history_days=safe_days)
    report["sync"] = sync
    checks.append(
        _check(
            "sync",
            bool(sync.get("ok")),
            "ok" if sync.get("ok") else str(sync.get("error") or "sync failed"),
        )
    )
    if sync.get("ok"):
        state = service.connections.get_sync_state(connection_id) or {}
        checks.append(
            _check(
                "mirror",
                state.get("status") == "ok",
                f"status {state.get('status')}, {state.get('positionsCount', 0)} position(s)",
            )
        )

    report["ok"] = all(item["ok"] for item in checks)
    if not report["ok"] and not report.get("error"):
        report["error"] = "one or more checks failed"
    return report


__all__ = ["run_smoke"]
