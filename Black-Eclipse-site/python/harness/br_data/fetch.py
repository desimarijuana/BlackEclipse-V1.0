"""Fetch + sync one Brazilian dataset, with the transport injected.

`sync` already knows how to turn a payload into rows and a run record; this module
is the missing middle: **where the bytes come from**, per dataset, because the
four publishers differ (a zip, a zip of CSVs, JSON, plain CSV).

The opener is injected for the same reason `download.py` injects it: tests run
against recorded fixtures and never touch a publisher, and a caller can supply a
retrying transport without this module growing a second HTTP stack.

A failure is raised, after the sync has recorded it — a scheduled job must be able
to tell "nothing new" from "the publisher refused".
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any, Callable, Optional

from . import bcb, cotahist, cvm, tesouro
from .csvtext import DatasetError, decode
from .download import Opener, download_archive, open_url
from .store import BrStore
from .sync import SyncReport, sync_archive, sync_dataset

#: Fallbacks used only when a caller does not pass a URL (tests pass fixtures).
DEFAULT_URLS: dict[str, str] = {
    "cotahist": "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP",
    cvm.DATASET: cvm.URL_TEMPLATE,
    tesouro.DATASET: tesouro.URL,
}


def _csv_member(payload: bytes) -> bytes:
    """The first `.csv` member of a publisher zip (CVM ships one per file)."""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                if info.filename.lower().endswith(".csv"):
                    with archive.open(info) as handle:
                        return handle.read()
    except zipfile.BadZipFile as exc:
        raise DatasetError("BAD_ARCHIVE", "the response is not a zip archive") from exc
    raise DatasetError("NO_RECORDS", "the archive has no .csv member")


def fetch_dataset(
    name: str,
    store: BrStore,
    *,
    dest_dir: str | Path = ".",
    opener: Optional[Opener] = None,
    url: Optional[str] = None,
    code: Optional[int] = None,
    year: Optional[int] = None,
    source: Optional[str] = None,
) -> SyncReport:
    """Fetch one dataset from its publisher and sync it into `store`.

    * `cotahist` -> zip, parsed by `sync_archive` (B3's fixed-width layout);
    * `cvm_inf_diario` -> zip of CSVs, the first CSV member parsed;
    * `bcb_sgs` -> the JSON series for `code` (required);
    * `tesouro_direto_preco_taxa` -> the CSV itself.

    The run is recorded under a **stable label** (the dataset id, or
    `<dataset>:<code>` for BCB) rather than the remote filename, because the
    scheduler asks "when did this dataset last succeed?" — a publisher's file name
    changes every month, which would make every month look like a first run.
    """
    opener_ = opener or open_url
    label = source or (f"{name}:{code}" if code is not None else name)
    target = url or DEFAULT_URLS.get(name, "")
    if name == "cotahist":
        if not target:
            raise DatasetError("NO_URL", "cotahist needs a url")
        resolved = target.format(year=year) if year else target.format(year="")
        path = download_archive(resolved, dest_dir, opener=opener_,
                               filename=f"cotahist_{year or 'latest'}.zip")
        return sync_archive(path, store, source=label)

    if name == cvm.DATASET:
        if not target:
            raise DatasetError("NO_URL", "the CVM dataset needs a url")
        payload = opener_(target, 120.0)
        if not isinstance(payload, (bytes, bytearray)):
            raise DatasetError("BAD_PAYLOAD", "the opener returned something that is not bytes")
        folder = Path(dest_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "cvm_inf_diario.zip").write_bytes(bytes(payload))
        return sync_dataset(name, _csv_member(bytes(payload)), store, source=label)

    if name == bcb.DATASET:
        if code is None:
            raise DatasetError("SERIES_CODE_REQUIRED", "bcb_sgs needs a series code")
        payload = opener_(target or bcb.url_for(code), 60.0)
        return sync_dataset(name, payload, store, code=code, source=label)

    if name == tesouro.DATASET:
        if not target:
            raise DatasetError("NO_URL", "the Tesouro dataset needs a url")
        payload = opener_(target, 60.0)
        return sync_dataset(name, payload, store, source=label)

    raise DatasetError("UNKNOWN_DATASET", f"no fetcher for {name!r}")


__all__ = ["DEFAULT_URLS", "Opener", "fetch_dataset"]
