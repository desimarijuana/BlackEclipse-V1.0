"""CVM / BCB / Tesouro parsers: decimal comma, blanks, typos, and refusals.

Every case uses a synthetic row shaped like the publisher's real output. The
assertions pin the things that silently corrupt financial data: a blank becoming
zero, a decimal comma read as a thousands separator, an unmapped BCB code
inventing a name, and the Tesouro file's `Mania` header typo.
"""

from __future__ import annotations

import pytest

from harness.br_data import bcb, cotahist, cvm, datasets, tesouro
from harness.br_data.csvtext import DatasetError, decode, iso_date, number, rows

# -- the shared primitives --------------------------------------------------

CVM_HEADER = ("TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;"
              "CAPTC_DIA;RESG_DIA;NR_COTST")


def test_decimal_comma_with_a_thousands_dot():
    assert number("1.234.567,89") == pytest.approx(1234567.89)


def test_plain_decimal_comma_and_negative():
    assert number("5,4321") == pytest.approx(5.4321)
    assert number("-3,5") == pytest.approx(-3.5)


def test_an_english_decimal_dot_still_parses():
    assert number("1234.56") == pytest.approx(1234.56)


def test_a_blank_cell_is_none_not_zero():
    for blank in ("", "  ", "-", "null", "N/A"):
        assert number(blank) is None


def test_junk_is_none_rather_than_an_exception():
    assert number("abc") is None


def test_dates_in_both_orders():
    assert iso_date("01/11/2026") == "2026-11-01"
    assert iso_date("2026-11-01") == "2026-11-01"
    assert iso_date("") == ""


def test_an_impossible_date_is_refused():
    with pytest.raises(DatasetError) as exc:
        iso_date("31/02/2026")
    assert exc.value.code == "BAD_DATE"


def test_latin1_and_utf8_both_decode():
    text = "Tipo Título;Data Base\n"
    assert "Título" in decode(text.encode("utf-8-sig"))
    assert "Título" in decode(text.encode("latin-1"))


def test_rows_strips_keys_and_drops_blank_lines():
    parsed = rows("a;b\n 1 ; 2 \n\n")
    assert parsed == [{"a": "1", "b": "2"}]


# -- CVM --------------------------------------------------------------------


def _cvm_text(*lines: str) -> str:
    return "\n".join([CVM_HEADER, *lines])


def test_cvm_normalizes_the_daily_fund_row():
    text = _cvm_text(
        "FI;00.000.000/0001-00;2026-11-01;1.234.567,89;12,345678;1.000.000,00;50.000,00;20.000,00;1234"
    )
    row = cvm.parse(text)[0]
    assert row["cnpj"] == "00.000.000/0001-00"
    assert row["date"] == "2026-11-01"
    assert row["quotaValue"] == pytest.approx(12.345678)
    assert row["netAssets"] == pytest.approx(1_000_000.0)
    assert row["netFlow"] == pytest.approx(30_000.0)
    assert row["derived"] == ["netFlow"]


def test_cvm_leaves_unreported_cells_empty_instead_of_zero():
    text = _cvm_text("FI;11.111.111/0001-11;2026-11-01;;;;;;")
    row = cvm.parse(text)[0]
    assert row["quotaValue"] is None
    assert row["netAssets"] is None
    assert row["netFlow"] is None          # no flows reported -> no derived number


def test_cvm_keeps_a_zero_flow_as_zero():
    text = _cvm_text("FI;22.222.222/0001-22;2026-11-01;1,0;1,0;1,0;0,00;0,00;10")
    row = cvm.parse(text)[0]
    assert row["netFlow"] == pytest.approx(0.0)


def test_cvm_skips_a_row_with_no_fund_identity():
    text = _cvm_text("FI;;2026-11-01;1;1;1;0;0;1", "FI;33.333.333/0001-33;2026-11-01;1;1;1;0;0;1")
    assert [r["cnpj"] for r in cvm.parse(text)] == ["33.333.333/0001-33"]


def test_cvm_refuses_a_header_only_file_and_an_empty_one():
    with pytest.raises(DatasetError) as exc:
        cvm.parse(CVM_HEADER)
    assert exc.value.code == "NO_ROWS"
    with pytest.raises(DatasetError) as empty:
        cvm.parse("   ")
    assert empty.value.code == "EMPTY"


# -- BCB --------------------------------------------------------------------


def test_bcb_parses_points_and_reports_the_series():
    payload = '[{"data":"01/11/2026","valor":"5,4321"},{"data":"04/11/2026","valor":"5,5"}]'
    result = bcb.parse(payload, 1)
    assert [p["value"] for p in result["points"]] == pytest.approx([5.4321, 5.5])
    assert result["points"][0]["date"] == "2026-11-01"
    assert result["meta"]["label"] == "USD/BRL PTAX (sell)"
    assert result["skipped"] == 0


def test_bcb_skips_and_counts_a_blank_observation():
    payload = '[{"data":"01/11/2026","valor":""},{"data":"04/11/2026","valor":"1,5"}]'
    result = bcb.parse(payload, 432)
    assert len(result["points"]) == 1
    assert result["skipped"] == 1     # a gap is visible, not papered over


def test_bcb_does_not_invent_a_name_for_an_unknown_code():
    result = bcb.parse('[{"data":"01/11/2026","valor":"1"}]', 999999)
    assert result["meta"]["label"] is None
    assert result["meta"]["known"] is False


def test_bcb_accepts_an_error_object_and_refuses_it():
    with pytest.raises(DatasetError) as exc:
        bcb.parse('{"error":"series not found"}', 1)
    assert exc.value.code == "BCB_ERROR"


def test_bcb_refuses_non_json():
    with pytest.raises(DatasetError) as exc:
        bcb.parse("<html>blocked</html>", 1)
    assert exc.value.code == "BAD_JSON"


def test_bcb_url_carries_the_window_only_when_given():
    assert bcb.url_for(11).endswith("/dados?formato=json")
    url = bcb.url_for(11, start="01/01/2026", end="01/06/2026")
    assert "dataInicial=01/01/2026" in url and "dataFinal=01/06/2026" in url


# -- Tesouro ----------------------------------------------------------------

TESOURO_HEADER = ("Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;"
                  "Taxa Venda Manha;PU Compra Mania;PU Venda Mania;PU Base Mania")


def _tesouro_text(*lines: str) -> str:
    return "\n".join([TESOURO_HEADER, *lines])


def test_tesouro_normalizes_a_bond_row_and_keeps_yields_as_percent():
    text = _tesouro_text(
        "Tesouro IPCA+ 2035;15/05/2035;01/11/2026;7,12;7,25;1.234,56;1.230,00;1.232,00"
    )
    row = tesouro.parse(text)[0]
    assert row["family"] == "Tesouro IPCA+"
    assert row["maturity"] == "2035-05-15"
    assert row["date"] == "2026-11-01"
    assert row["buyYield"] == pytest.approx(7.12)      # percent, not 0.0712
    assert row["yieldUnit"] == "% per year"
    assert row["buyPrice"] == pytest.approx(1234.56)


def test_tesouro_accepts_the_corrected_accented_header():
    text = "\n".join([
        "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manhã;Taxa Venda Manhã;"
        "PU Compra Manhã;PU Venda Manhã;PU Base Manhã",
        "Tesouro Selic 2029;01/03/2029;01/11/2026;0,05;0,06;15.000,00;14.999,00;15.000,00",
    ])
    row = tesouro.parse(text)[0]
    assert row["sellPrice"] == pytest.approx(14999.0)


def test_tesouro_keeps_a_zero_price_and_blanks_a_missing_one():
    text = _tesouro_text(
        "Tesouro Prefixado 2030;01/01/2030;01/11/2026;10,5;;;;0,00",
    )
    row = tesouro.parse(text)[0]
    assert row["buyPrice"] is None
    assert row["basePrice"] == pytest.approx(0.0)


def test_tesouro_detects_a_comma_delimited_file():
    # In a comma-delimited export the decimal separator must be a dot — an
    # unquoted "0,05" would be two fields, so this variant is not ambiguous.
    text = "\n".join([
        "Tipo Titulo,Data Vencimento,Data Base,Taxa Compra Manha,Taxa Venda Manha,"
        "PU Compra Mania,PU Venda Mania,PU Base Mania",
        "Tesouro Selic 2029,01/03/2029,01/11/2026,0.05,0.06,15000.00,14999.00,15000.00",
    ])
    assert tesouro.parse(text)[0]["buyYield"] == pytest.approx(0.05)


def test_an_unknown_bond_family_is_blank_not_guessed():
    assert tesouro.family("LFT 2029") == ""
    assert tesouro.family("Tesouro Selic 2029") == "Tesouro Selic"


# -- the registry -----------------------------------------------------------


def test_the_registry_lists_all_four_datasets_with_a_source():
    listed = {row["id"]: row for row in datasets.list_datasets()}
    assert set(listed) == {"cotahist", cvm.DATASET, bcb.DATASET, tesouro.DATASET}
    assert all(row["source"] and row["shape"] and row["url"] for row in listed.values())


def test_parse_dataset_routes_to_the_right_parser():
    rows_out = datasets.parse_dataset(cvm.DATASET, _cvm_text(
        "FI;44.444.444/0001-44;2026-11-01;1;1;1;0;0;1"))
    assert rows_out[0]["dataset"] == cvm.DATASET
    assert datasets.parse_dataset(tesouro.DATASET, _tesouro_text(
        "Tesouro Selic 2029;01/03/2029;01/11/2026;0,05;0,06;1;1;1"))[0]["bond"].startswith("Tesouro")
    assert datasets.parse_dataset(
        bcb.DATASET, '[{"data":"01/11/2026","valor":"1"}]', code=11)["meta"]["code"] == 11


def test_parse_dataset_requires_a_series_code_and_refuses_unknown_names():
    with pytest.raises(DatasetError) as exc:
        datasets.parse_dataset(bcb.DATASET, "[]")
    assert exc.value.code == "SERIES_CODE_REQUIRED"
    with pytest.raises(DatasetError) as unknown:
        datasets.parse_dataset("no_such_dataset", "x")
    assert unknown.value.code == "UNKNOWN_DATASET"


def test_cotahist_is_still_reachable_through_the_registry():
    assert datasets.parse_dataset("cotahist", "") == []
