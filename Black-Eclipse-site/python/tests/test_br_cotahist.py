"""COTAHIST fixed-width parsing: positions, implied decimals, FATCOT, errors."""

from __future__ import annotations

import pytest

from harness.br_data import cotahist as C

WIDTH = {name: end - start + 1 for name, (start, end) in C.COLUMNS.items()}


def _record(**fields) -> str:
    """Build a 245-character record with each value at its published position."""
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
        text = str(defaults[name])[: WIDTH[name]].ljust(WIDTH[name])
        buf[start - 1:end] = list(text)
    line = "".join(buf)
    assert len(line) == C.RECORD_LENGTH
    return line


def test_positions_match_the_published_layout():
    assert C.RECORD_LENGTH == 245
    assert C.COLUMNS["trade_date"] == (3, 10)
    assert C.COLUMNS["ticker"] == (13, 24)
    assert C.COLUMNS["close"] == (109, 121)
    assert C.COLUMNS["factor"] == (211, 217)
    assert C.COLUMNS["isin"] == (231, 242)


def test_a_record_parses_into_normalized_fields():
    row = C.parse_record(_record())
    assert row is not None
    assert row["tradeDate"] == "2024-01-02"
    assert row["ticker"] == "PETR4"
    assert row["spec"] == "PN N2"
    assert row["marketType"] == 10
    assert row["trades"] == 42
    assert row["quantity"] == 1000
    assert row["isin"] == "BRPETRACNPR6"


def test_prices_have_two_implied_decimals():
    row = C.parse_record(_record())
    assert row["open"] == pytest.approx(10.50)
    assert row["high"] == pytest.approx(11.00)
    assert row["low"] == pytest.approx(10.00)
    assert row["close"] == pytest.approx(10.80)
    assert row["volume"] == pytest.approx(1080.00)


def test_a_lot_quoted_record_exposes_the_unit_price():
    row = C.parse_record(_record(factor="0001000", close="0000001050000"))
    assert row["close"] == pytest.approx(10500.00)
    assert row["factor"] == 1000
    # per-share price divides the quote factor out; the raw value is kept
    assert row["unitPrice"]["close"] == pytest.approx(10.50)


def test_a_one_factor_record_does_not_divide():
    row = C.parse_record(_record())
    assert row["unitPrice"]["close"] == pytest.approx(row["close"])


def test_the_header_and_trailer_are_not_rows():
    assert C.parse_record(_record(record_type="00")) is None
    assert C.parse_record(_record(record_type="99")) is None


def test_a_file_skips_the_header_and_trailer():
    text = "\n".join([_record(record_type="00"), _record(), _record(record_type="99")])
    rows = C.parse_records(text)
    assert len(rows) == 1


def test_a_wrong_length_is_a_named_error():
    with pytest.raises(C.CotahistError) as exc:
        C.parse_record(_record()[:-5])
    assert exc.value.code == "BAD_LENGTH"


def test_a_bad_price_is_a_named_error():
    with pytest.raises(C.CotahistError) as exc:
        C.parse_record(_record(close="0000000AB000"))
    assert exc.value.code == "BAD_PRICE"


def test_an_error_names_the_line_number():
    text = "\n".join([_record(), _record(close="0000000AB000")])
    with pytest.raises(C.CotahistError) as exc:
        C.parse_records(text)
    assert "line 2" in str(exc.value)


def test_zero_dates_are_empty_not_an_exception():
    row = C.parse_record(_record(expiration_date="00000000", exercise_price="0000000000000"))
    assert row["expirationDate"] == ""
    assert row["exercisePrice"] == pytest.approx(0.0)


def test_latin1_names_survive_decoding():
    line = _record(short_name="PETROBRAS").encode("latin-1").decode("latin-1")
    assert C.parse_record(line)["shortName"] == "PETROBRAS"


def test_iter_records_streams_without_collecting():
    rows = list(C.iter_records([_record(), _record(ticker="VALE3")]))
    assert [r["ticker"] for r in rows] == ["PETR4", "VALE3"]
