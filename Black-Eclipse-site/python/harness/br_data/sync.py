"""COTAHIST archive sync — read a local .zip, parse it, upsert into the store.

The sync is a **pure function of a local file**: it never downloads. That keeps
it testable offline and lets the caller decide how the archive arrives (manual
download, a scheduler, or a future `download` step). It reads the first member
that looks like a COTAHIST text file, decodes Latin-1, streams records, and
upserts them.

Idempotency is the contract: syncing the same archive twice leaves the row count
unchanged and reports the second pass as `updated` rather than `inserted`. A
failed run is recorded in `sync_runs` with its error and re-raised — the caller
must not have to guess whether the store is current.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .cotahist import CotahistError, iter_records
from .datasets import parse_dataset
from .store import BrStore


@dataclass
class SyncReport:
    source: str
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    status: str = "ok"
    error: str = ""
    trade_dates: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "rows": self.rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "status": self.status,
            "error": self.error or None,
            "tradeDates": list(self.trade_dates),
        }


def _text_member(archive: zipfile.ZipFile) -> str:
    """The archive member that holds records: a .txt/.csv, or an extensionless file."""
    for info in archive.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if name.lower().endswith((".txt", ".csv")) or Path(name).suffix == "":
            return name
    raise CotahistError("NO_RECORDS", "the archive has no text member to parse")


def read_archive(path: str | Path) -> list[dict[str, Any]]:
    """Parse every quote record in a local COTAHIST zip."""
    file = Path(path)
    if not file.exists():
        raise CotahistError("NOT_FOUND", f"archive not found: {file}")
    try:
        with zipfile.ZipFile(file) as archive:
            member = _text_member(archive)
            with archive.open(member) as handle:
                text = handle.read().decode("latin-1")
    except zipfile.BadZipFile as exc:
        raise CotahistError("BAD_ARCHIVE", f"{file.name} is not a zip archive") from exc
    return list(iter_records(text.splitlines()))


def sync_archive(path: str | Path, store: BrStore, *, source: Optional[str] = None) -> SyncReport:
    """Parse `path` and upsert it. Records the run either way, re-raises on failure."""
    label = source or Path(path).name
    run_id = store.start_run(label)
    report = SyncReport(source=label)
    try:
        rows = read_archive(path)
        inserted, updated, skipped = store.upsert(rows)
        report.rows, report.inserted, report.updated, report.skipped = (
            len(rows), inserted, updated, skipped)
        report.trade_dates = tuple(sorted({str(r.get("tradeDate")) for r in rows if r.get("tradeDate")}))
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised for the caller
        code = getattr(exc, "code", "")
        report.status = "failed"
        report.error = f"{type(exc).__name__}[{code}]: {exc}"[:500] if code else f"{type(exc).__name__}: {exc}"[:500]
        store.finish_run(run_id, rows=report.rows, inserted=report.inserted,
                         updated=report.updated, status="failed", error=report.error)
        raise
    store.finish_run(run_id, rows=report.rows, inserted=report.inserted,
                     updated=report.updated, status="ok")
    return report


def sync_dataset(
    name: str,
    payload: bytes | str,
    store: BrStore,
    *,
    code: Optional[int] = None,
    source: Optional[str] = None,
) -> SyncReport:
    """Parse one dataset payload and upsert it, recording the run either way.

    `source` defaults to `<dataset>` (plus the series code for BCB), so two series
    synced from the same store are distinguishable in `sync_runs`.
    """
    label = source or (f"{name}:{code}" if code is not None else name)
    run_id = store.start_run(label)
    report = SyncReport(source=label)
    try:
        rows = parse_dataset(name, payload, **({"code": code} if code is not None else {}))
        if name == "bcb_sgs":
            points = list(rows.get("points") or [])
            report.skipped = int(rows.get("skipped") or 0)
        else:
            points = list(rows or [])
        inserted, updated, skipped = store.upsert_dataset(name, points)
        report.rows = len(points)
        report.inserted, report.updated = inserted, updated
        report.skipped += skipped
        report.trade_dates = tuple(sorted({
            str(row.get("date") or row.get("trade_date"))
            for row in points if row.get("date") or row.get("trade_date")
        }))
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised for the caller
        code_ = getattr(exc, "code", "")
        report.status = "failed"
        report.error = (
            f"{type(exc).__name__}[{code_}]: {exc}"[:500]
            if code_ else f"{type(exc).__name__}: {exc}"[:500]
        )
        store.finish_run(run_id, rows=report.rows, inserted=report.inserted,
                         updated=report.updated, status="failed", error=report.error)
        raise
    store.finish_run(run_id, rows=report.rows, inserted=report.inserted,
                     updated=report.updated, status="ok")
    return report


__all__ = ["SyncReport", "read_archive", "sync_archive", "sync_dataset"]
