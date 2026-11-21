"""B3 download: recorded-fixture fetch, atomic write, then the normal sync path."""

from __future__ import annotations

import io
import urllib.error
import zipfile

import pytest

from harness.br_data import cotahist as C
from harness.br_data.download import (
    DownloadError,
    download_archive,
    sync_from_url,
)
from harness.br_data.store import BrStore

WIDTH = {name: end - start + 1 for name, (start, end) in C.COLUMNS.items()}


def _record(**fields) -> str:
    defaults = {
        "record_type": "01", "trade_date": "20240102", "bdi": "02",
        "ticker": "PETR4", "market_type": "010", "short_name": "PETROBRAS",
        "spec": "PN N2", "open": "0000000001050", "high": "0000000001100",
        "low": "0000000001000", "average": "0000000001060",
        "close": "0000000001080", "best_bid": "0000000001070",
        "best_ask": "0000000001085", "trades": "00042",
        "quantity": "000000000001000", "volume": "00000000000108000",
        "exercise_price": "0000000000000", "expiration_date": "00000000",
        "factor": "0000001", "isin": "BRPETRACNPR6",
    }
    defaults.update(fields)
    buf = [" "] * C.RECORD_LENGTH
    for name, (start, end) in C.COLUMNS.items():
        buf[start - 1:end] = list(str(defaults[name])[: WIDTH[name]].ljust(WIDTH[name]))
    return "".join(buf)


def _zip_bytes(lines) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("COTAHIST_A2024.TXT", "\n".join(lines))
    return buffer.getvalue()


@pytest.fixture()
def store(tmp_path):
    return BrStore(tmp_path / "br.db")


def test_download_writes_the_archive_atomically(tmp_path):
    payload = _zip_bytes([_record()])
    path = download_archive("https://b3.example/COTAHIST_A2024.ZIP",
                            tmp_path / "in", opener=lambda url, timeout: payload)
    assert path.exists() and path.read_bytes() == payload
    assert not list(path.parent.glob("*.part")), "a .part file must not survive"


def test_download_honours_an_explicit_filename(tmp_path):
    path = download_archive("https://b3.example/x", tmp_path, filename="today.zip",
                            opener=lambda url, timeout: _zip_bytes([_record()]))
    assert path.name == "today.zip"


def test_sync_from_url_parses_and_upserts(tmp_path, store):
    payload = _zip_bytes([_record(), _record(ticker="VALE3")])
    report = sync_from_url("https://b3.example/COTAHIST_A2024.ZIP", store,
                           tmp_path / "in", opener=lambda url, timeout: payload)
    assert report.status == "ok"
    assert (report.rows, report.inserted) == (2, 2)
    assert store.count() == 2


def test_sync_from_url_is_idempotent(tmp_path, store):
    payload = _zip_bytes([_record()])
    opener = lambda url, timeout: payload  # noqa: E731
    first = sync_from_url("https://b3.example/a.zip", store, tmp_path / "in", opener=opener)
    second = sync_from_url("https://b3.example/a.zip", store, tmp_path / "in", opener=opener)
    assert (first.inserted, second.inserted) == (1, 0)
    assert store.count() == 1


def test_a_non_zip_payload_is_refused_before_it_reaches_disk(tmp_path, store):
    with pytest.raises(DownloadError) as exc:
        download_archive("https://b3.example/x", tmp_path / "in",
                         opener=lambda url, timeout: b"<html>maintenance</html>")
    assert exc.value.code == "NOT_ZIP"
    assert not list((tmp_path / "in").glob("*"))


def test_a_non_bytes_payload_is_refused(tmp_path):
    with pytest.raises(DownloadError) as exc:
        download_archive("https://b3.example/x", tmp_path, opener=lambda url, timeout: "text")
    assert exc.value.code == "BAD_PAYLOAD"


def test_an_oversized_payload_is_refused(tmp_path, monkeypatch):
    import harness.br_data.download as D

    monkeypatch.setattr(D, "MAX_BYTES", 10)
    with pytest.raises(DownloadError) as exc:
        download_archive("https://b3.example/x", tmp_path,
                         opener=lambda url, timeout: b"PK" + b"0" * 100)
    assert exc.value.code == "TOO_LARGE"


def test_the_urllib_opener_maps_http_errors(monkeypatch):
    import harness.br_data.download as D

    def raising(*args, **kwargs):
        raise urllib.error.HTTPError("https://x", 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setattr("urllib.request.urlopen", raising)
    with pytest.raises(DownloadError) as exc:
        D._urllib_opener("https://x", 5.0)
    assert exc.value.code == "HTTP_404"


def test_the_urllib_opener_maps_unreachable_hosts(monkeypatch):
    import harness.br_data.download as D

    def raising(*args, **kwargs):
        raise urllib.error.URLError("dns failure")

    monkeypatch.setattr("urllib.request.urlopen", raising)
    with pytest.raises(DownloadError) as exc:
        D._urllib_opener("https://x", 5.0)
    assert exc.value.code == "UNREACHABLE"


def test_a_failed_download_records_nothing(tmp_path, store):
    with pytest.raises(DownloadError):
        sync_from_url("https://b3.example/x", store, tmp_path / "in",
                      opener=lambda url, timeout: b"not a zip")
    assert store.count() == 0
    assert store.status()["lastRun"] is None
