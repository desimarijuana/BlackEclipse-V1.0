"""COTAHIST archive sync: idempotent upsert, status, and honest failures."""

from __future__ import annotations

import zipfile

import pytest

from harness.br_data import cotahist as C
from harness.br_data.store import BrStore
from harness.br_data.sync import read_archive, sync_archive

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


def _zip(tmp_path, lines, name="COTAHIST_A2024.ZIP", member="COTAHIST_A2024.TXT"):
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, "\n".join(lines))
    return path


@pytest.fixture()
def store(tmp_path):
    return BrStore(tmp_path / "br.db")


def test_sync_parses_and_inserts(tmp_path, store):
    path = _zip(tmp_path, [_record(record_type="00"), _record(), _record(ticker="VALE3")])
    report = sync_archive(path, store)
    assert report.status == "ok"
    assert (report.rows, report.inserted, report.updated) == (2, 2, 0)
    assert report.trade_dates == ("2024-01-02",)
    assert store.count() == 2


def test_rows_are_queryable_after_sync(tmp_path, store):
    sync_archive(_zip(tmp_path, [_record()]), store)
    rows = store.quotes(ticker="PETR4")
    assert rows[0]["close"] == pytest.approx(10.80)
    assert rows[0]["trade_date"] == "2024-01-02"
    assert rows[0]["factor"] == 1


def test_resyncing_the_same_archive_is_idempotent(tmp_path, store):
    path = _zip(tmp_path, [_record()])
    first = sync_archive(path, store)
    second = sync_archive(path, store)
    assert (first.inserted, second.inserted) == (1, 0)
    assert second.updated == 1
    assert store.count() == 1


def test_a_changed_quote_updates_in_place(tmp_path, store):
    sync_archive(_zip(tmp_path, [_record()], name="a.zip"), store)
    sync_archive(_zip(tmp_path, [_record(close="0000000001200")], name="b.zip"), store)
    rows = store.quotes(ticker="PETR4")
    assert store.count() == 1
    assert rows[0]["close"] == pytest.approx(12.00)


def test_a_duplicate_within_one_file_keeps_the_last(tmp_path, store):
    path = _zip(tmp_path, [_record(), _record(close="0000000002000")])
    report = sync_archive(path, store)
    assert report.rows == 2
    assert store.count() == 1
    assert store.quotes(ticker="PETR4")[0]["close"] == pytest.approx(20.00)


def test_rows_without_a_key_are_skipped_and_counted(tmp_path, store):
    path = _zip(tmp_path, [_record(ticker="      ")])
    report = sync_archive(path, store)
    assert report.skipped == 1
    assert store.count() == 0


def test_status_reports_counts_and_the_last_run(tmp_path, store):
    sync_archive(_zip(tmp_path, [_record()]), store)
    status = store.status()
    assert status["quotes"] == 1
    assert status["firstTradeDate"] == status["lastTradeDate"] == "2024-01-02"
    assert status["lastRun"]["status"] == "ok"
    assert status["lastRun"]["inserted"] == 1


def test_a_non_zip_is_a_named_error_and_is_recorded(tmp_path, store):
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip", encoding="utf-8")
    with pytest.raises(C.CotahistError) as exc:
        sync_archive(bad, store)
    assert exc.value.code == "BAD_ARCHIVE"
    last = store.status()["lastRun"]
    assert last["status"] == "failed"
    assert "BAD_ARCHIVE" in (last["error"] or "")


def test_an_archive_with_no_text_member_is_refused(tmp_path, store):
    path = tmp_path / "empty.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data.bin", b"\x00\x01")
    with pytest.raises(C.CotahistError) as exc:
        sync_archive(path, store)
    assert exc.value.code == "NO_RECORDS"


def test_read_archive_returns_parsed_rows_without_a_store(tmp_path):
    rows = read_archive(_zip(tmp_path, [_record(), _record(record_type="99")]))
    assert len(rows) == 1 and rows[0]["ticker"] == "PETR4"


def test_a_missing_archive_is_named(tmp_path, store):
    with pytest.raises(C.CotahistError) as exc:
        sync_archive(tmp_path / "nope.zip", store)
    assert exc.value.code == "NOT_FOUND"
