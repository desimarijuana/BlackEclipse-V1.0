"""Scheduled registration for the Brazilian datasets.

A dataset that must be refreshed by hand is a dataset that goes stale silently,
so this module answers two questions with data rather than a prompt:

  * **is it due?** `due_datasets()` compares each dataset's last successful run
    (from `sync_runs`) against its cadence. A dataset that has never run is due.
    A dataset whose last run *failed* is due again — a failure must not be
    mistaken for freshness.
  * **what happened?** `sync_due()` runs each due fetch, records the outcome, and
    continues past a failure so one unreachable publisher cannot block the others.

**Off by default.** `start_br_sync()` returns `None` unless `BE_BR_SYNC=1`, because
a boot that silently downloads tens of megabytes from four publishers is not
something to do to an operator uninvited. When enabled, the loop wakes hourly and
asks `due_datasets` — the cadence lives in `SCHEDULES`, not in the sleep.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from . import bcb, cvm, tesouro
from .csvtext import DatasetError
from .fetch import fetch_dataset
from .store import BrStore

log = logging.getLogger("harness.br_data.schedule")

#: Every dataset is published at most daily; 24h keeps a re-sync rare but real.
SCHEDULES: dict[str, dict[str, Any]] = {
    "cotahist": {"every_hours": 24, "note": "B3 publishes after the close"},
    cvm.DATASET: {"every_hours": 24, "note": "CVM's monthly file is appended daily"},
    bcb.DATASET: {"every_hours": 24, "note": "SGS observations are daily or monthly"},
    tesouro.DATASET: {"every_hours": 24, "note": "Tesouro publishes business days"},
}

#: Which datasets need a series code (BCB only). One entry per series to sync.
DEFAULT_SERIES: tuple[int, ...] = (1, 11, 432, 433)


def _parse(iso: Any) -> Optional[datetime]:
    text = str(iso or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def last_success(store: BrStore, label: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """The most recent OK run for `label`, or None.

    Only `status='ok'` runs count: a failed run recorded five minutes ago is
    evidence of a problem, not of freshness.
    """
    del now  # kept in the signature so callers need no branch for "now"
    with store._connect() as conn:  # noqa: SLF001 - the store's own file
        row = conn.execute(
            "SELECT finished_at FROM sync_runs WHERE source=? AND status='ok' "
            "ORDER BY id DESC LIMIT 1",
            (label,),
        ).fetchone()
    return _parse(row[0]) if row else None


def due_datasets(
    store: BrStore,
    now: Optional[datetime] = None,
    *,
    series: tuple[int, ...] = DEFAULT_SERIES,
    schedules: Optional[dict[str, dict[str, Any]]] = None,
) -> list[str]:
    """The dataset labels that are due, in schedule order.

    A label is `<dataset>` or, for BCB, `<dataset>:<code>` — one per series.
    """
    moment = now or datetime.now(timezone.utc)
    plan = schedules or SCHEDULES
    labels: list[str] = []
    for name, spec in plan.items():
        labels.extend(
            f"{bcb.DATASET}:{code}" for code in series
        ) if name == bcb.DATASET else labels.append(name)
    due: list[str] = []
    for label in labels:
        name = label.split(":", 1)[0]
        hours = float((plan.get(name) or {}).get("every_hours") or 24)
        last = last_success(store, label, moment)
        if last is None or moment - last >= timedelta(hours=hours):
            due.append(label)
    return due


def sync_due(
    store: BrStore,
    *,
    dest_dir: str | Path = ".",
    opener: Optional[Callable[[str, float], bytes]] = None,
    now: Optional[datetime] = None,
    series: tuple[int, ...] = DEFAULT_SERIES,
    url_for: Optional[Callable[[str, Optional[int]], Optional[str]]] = None,
    schedules: Optional[dict[str, dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Fetch every due dataset. One failure never stops the others.

    Returns one outcome per attempted label: `{dataset, status, rows, inserted,
    updated, skipped, error}`. A failure is reported here and recorded in
    `sync_runs` by the sync itself, so the next pass sees it as due.
    """
    outcomes: list[dict[str, Any]] = []
    for label in due_datasets(store, now, series=series, schedules=schedules):
        name = label.split(":", 1)[0]
        code = int(label.split(":", 1)[1]) if ":" in label else None
        url = url_for(name, code) if url_for else None
        try:
            report = fetch_dataset(name, store, dest_dir=dest_dir, opener=opener,
                                   url=url, code=code,
                                   year=(now or datetime.now(timezone.utc)).year)
            outcomes.append({
                "dataset": label,
                "status": report.status,
                "rows": report.rows,
                "inserted": report.inserted,
                "updated": report.updated,
                "skipped": report.skipped,
                "error": report.error or None,
            })
        except (DatasetError, Exception) as exc:  # noqa: BLE001 - reported, not raised
            code_ = getattr(exc, "code", "")
            outcomes.append({
                "dataset": label,
                "status": "failed",
                "rows": 0,
                "error": f"{type(exc).__name__}[{code_}]: {exc}"[:500],
            })
            log.warning("brazilian dataset %s failed to sync: %s", label, exc)
    return outcomes


async def sync_loop(
    store: BrStore,
    *,
    dest_dir: str | Path = ".",
    opener: Optional[Callable[[str, float], bytes]] = None,
    interval_s: float = 3600.0,
    stop: Optional[asyncio.Event] = None,
) -> None:
    """Wake every `interval_s` and sync whatever is due. Cancellable."""
    halt = stop or asyncio.Event()
    while not halt.is_set():
        try:
            outcomes = await asyncio.to_thread(sync_due, store, dest_dir=dest_dir,
                                              opener=opener)
            if outcomes:
                log.info("brazilian dataset sync: %s", outcomes)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a scheduler must survive a bad pass
            log.warning("brazilian dataset sync pass failed", exc_info=True)
        try:
            await asyncio.wait_for(halt.wait(), timeout=max(60.0, float(interval_s)))
        except asyncio.TimeoutError:
            continue


def br_sync_enabled() -> bool:
    """Opt-in: `BE_BR_SYNC=1`. Anything else (including unset) is off."""
    return str(os.environ.get("BE_BR_SYNC") or "").strip().lower() in ("1", "true", "yes", "on")


def start_br_sync(service: Any, *, store: Optional[BrStore] = None,
                  dest_dir: Optional[str | Path] = None) -> Optional[asyncio.Task]:
    """Register the loop on the running service, or return None when disabled.

    The store defaults to the service's data directory (`br_data.db`), not to the
    current working directory: a scheduled job must write where the app reads.
    """
    if not br_sync_enabled():
        log.info("brazilian dataset sync is disabled (set BE_BR_SYNC=1 to enable)")
        return None
    root = Path(getattr(service, "data_dir", None) or os.environ.get("HARNESS_DATA_DIR") or ".")
    folder = Path(dest_dir) if dest_dir else root / "br_data"
    folder.mkdir(parents=True, exist_ok=True)
    db = store or BrStore(root / "br_data.db")
    task = asyncio.create_task(sync_loop(db, dest_dir=folder))
    try:
        setattr(service, "_br_sync_task", task)
    except Exception:  # noqa: BLE001 - a service that forbids attributes still runs
        pass
    log.info("brazilian dataset sync started (every 3600s)")
    return task


__all__ = [
    "DEFAULT_SERIES",
    "SCHEDULES",
    "br_sync_enabled",
    "due_datasets",
    "last_success",
    "start_br_sync",
    "sync_due",
    "sync_loop",
]
