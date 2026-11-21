"""Brazilian official market data parsers (offline; no sync or network here)."""

from __future__ import annotations

from . import bcb, cotahist, cvm, tesouro
from .cotahist import (
    COLUMNS,
    CotahistError,
    RECORD_LENGTH,
    iter_records,
    parse_record,
    parse_records,
)
from .csvtext import DatasetError, decode, iso_date, number
from .datasets import DATASETS, list_datasets, parse_dataset
from .download import DownloadError, download_archive, sync_from_url
from .store import BrStore
from .sync import SyncReport, read_archive, sync_archive, sync_dataset

__all__ = [
    "COLUMNS",
    "BrStore",
    "CotahistError",
    "DATASETS",
    "DatasetError",
    "DownloadError",
    "RECORD_LENGTH",
    "SyncReport",
    "bcb",
    "cotahist",
    "cvm",
    "decode",
    "download_archive",
    "iso_date",
    "iter_records",
    "list_datasets",
    "number",
    "parse_dataset",
    "parse_record",
    "parse_records",
    "read_archive",
    "sync_archive",
    "sync_dataset",
    "sync_from_url",
    "tesouro",
]
