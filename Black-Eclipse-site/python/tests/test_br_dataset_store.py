"""The three datasets' store tables: keys, idempotency, and what is not stored.

The properties pinned here are the ones a scheduled sync depends on:

  * syncing the same payload twice leaves the row count unchanged and reports the
    second pass as `updated`, not `inserted`;
  * the key differs per dataset (fund CNPJ, BCB series, bond name) and two BCB
    series coexist;
  * a row missing its key is **skipped and counted**, never written under an
    empty key;
  * the CVM `netFlow` is **not** stored — it is arithmetic over two stored columns;
  * a blank price stays `NULL` (distinct from `0.0`);
  * a failed sync is recorded in `sync_runs` with its code and re-raised.
"""

from __future__ import annotations

import pytest

from harness.br_data import bcb, cvm, sync, tesouro
from harness.br_data.store import BrStore

CVM_HEADER = ("TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;"
              "CAPTC_DIA;RESG_DIA;NR_COTST")
TESOURO_HEADER = ("Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;"
                  "Taxa Venda Manha;PU Compra Mania;PU Venda Mania;PU Base Mania")


def _cvm(*lines: str) -> str:
    return "\n".join([CVM_HEADER, *lines])


def _tesouro(*lines: str) -> str:
    return "\n".join([TESOURO_HEADER, *lines])


def _bcb(*points: str) -> str:
    return "[" + ",".join(points) + "]"


@pytest.fixture()
def store(tmp_path) -> BrStore:
    return BrStore(tmp_path / "br.db")


# -- CVM --------------------------------------------------------------------


def test_cvm_sync_is_idempotent_and_reports_updates(store):
    payload = _cvm(
        "FI;00.000.000/0001-00;2026-11-01;1.000,00;12,5;1.000,00;10,00;4,00;100",
        "FI;11.111.111/0001-11;2026-11-01;2.000,00;25,0;2.000,00;0,00;0,00;50",
    )
    first = sync.sync_dataset(cvm.DATASET, payload, store)
    assert (first.rows, first.inserted, first.updated) == (2, 2, 0)
    assert store.dataset_counts()[cvm.DATASET] == 2

    second = sync.sync_dataset(cvm.DATASET, payload, store)
    assert (second.inserted, second.updated) == (0, 2)
    assert store.dataset_counts()[cvm.DATASET] == 2      # no duplicates


def test_a_corrected_value_overwrites_the_row(store):
    sync.sync_dataset(cvm.DATASET, _cvm(
        "FI;22.222.222/0001-22;2026-11-01;1,0;10,0;1,0;0;0;1"), store)
    sync.sync_dataset(cvm.DATASET, _cvm(
        "FI;22.222.222/0001-22;2026-11-01;1,0;11,0;1,0;0;0;1"), store)
    row = store.dataset_rows(cvm.DATASET, key="22.222.222/0001-22")[0]
    assert row["quota_value"] == pytest.approx(11.0)


def test_the_derived_net_flow_is_not_stored_but_is_recoverable(store):
    sync.sync_dataset(cvm.DATASET, _cvm(
        "FI;33.333.333/0001-33;2026-11-01;1,0;1,0;1,0;10,00;4,00;1"), store)
    row = store.dataset_rows(cvm.DATASET)[0]
    assert "net_flow" not in row
    assert row["contributions"] - row["redemptions"] == pytest.approx(6.0)


def test_a_blank_cell_is_null_not_zero_in_the_store(store):
    sync.sync_dataset(cvm.DATASET, _cvm(
        "FI;44.444.444/0001-44;2026-11-01;;;;;;1"), store)
    row = store.dataset_rows(cvm.DATASET)[0]
    assert row["quota_value"] is None
    assert row["contributions"] is None


# -- BCB --------------------------------------------------------------------


def test_two_series_coexist_and_are_keyed_by_code(store):
    sync.sync_dataset(bcb.DATASET, _bcb(
        '{"data":"01/11/2026","valor":"5,43"}'), store, code=1)
    sync.sync_dataset(bcb.DATASET, _bcb(
        '{"data":"01/11/2026","valor":"10,5"}'), store, code=432)
    assert store.dataset_counts()[bcb.DATASET] == 2
    assert store.dataset_rows(bcb.DATASET, key=1)[0]["value"] == pytest.approx(5.43)
    assert store.dataset_rows(bcb.DATASET, key=432)[0]["value"] == pytest.approx(10.5)


def test_the_same_series_synced_twice_updates(store):
    payload = _bcb('{"data":"01/11/2026","valor":"5,43"}')
    sync.sync_dataset(bcb.DATASET, payload, store, code=1)
    again = sync.sync_dataset(bcb.DATASET, payload, store, code=1)
    assert (again.inserted, again.updated) == (0, 1)
    assert store.dataset_counts()[bcb.DATASET] == 1


def test_a_skipped_bcb_observation_is_reported(store):
    payload = _bcb('{"data":"01/11/2026","valor":""}',
                   '{"data":"04/11/2026","valor":"5,5"}')
    report = sync.sync_dataset(bcb.DATASET, payload, store, code=1)
    assert report.rows == 1
    assert report.skipped == 1


def test_each_bcb_series_is_named_in_the_run_log(store):
    sync.sync_dataset(bcb.DATASET, _bcb('{"data":"01/11/2026","valor":"1"}'), store, code=11)
    assert store.status()["lastRun"]["source"] == f"{bcb.DATASET}:11"


# -- Tesouro ----------------------------------------------------------------


def test_tesouro_is_keyed_by_bond_and_date(store):
    payload = _tesouro(
        "Tesouro Selic 2029;01/03/2029;01/11/2026;0,05;0,06;15.000,00;14.999,00;15.000,00",
        "Tesouro IPCA+ 2035;15/05/2035;01/11/2026;7,12;7,25;1.234,56;1.230,00;1.232,00",
    )
    first = sync.sync_dataset(tesouro.DATASET, payload, store)
    assert (first.rows, first.inserted) == (2, 2)
    again = sync.sync_dataset(tesouro.DATASET, payload, store)
    assert (again.inserted, again.updated) == (0, 2)
    assert store.dataset_counts()[tesouro.DATASET] == 2


def test_tesouro_keeps_a_zero_price_and_a_null_price_distinct(store):
    sync.sync_dataset(tesouro.DATASET, _tesouro(
        "Tesouro Prefixado 2030;01/01/2030;01/11/2026;10,5;;;;0,00"), store)
    row = store.dataset_rows(tesouro.DATASET)[0]
    assert row["buy_price"] is None
    assert row["base_price"] == pytest.approx(0.0)


def test_tesouro_yields_are_stored_as_published_percent(store):
    sync.sync_dataset(tesouro.DATASET, _tesouro(
        "Tesouro IPCA+ 2035;15/05/2035;01/11/2026;7,12;7,25;1;1;1"), store)
    assert store.dataset_rows(tesouro.DATASET)[0]["buy_yield"] == pytest.approx(7.12)


# -- failure + isolation ----------------------------------------------------


def test_a_failed_sync_is_recorded_and_re_raised(store):
    with pytest.raises(Exception) as exc:
        sync.sync_dataset(cvm.DATASET, "", store)
    assert getattr(exc.value, "code", "") == "EMPTY"
    run = store.status()["lastRun"]
    assert run["status"] == "failed"
    assert "EMPTY" in (run["error"] or "")


def test_a_missing_series_code_fails_before_writing(store):
    with pytest.raises(Exception) as exc:
        sync.sync_dataset(bcb.DATASET, "[]", store)
    assert getattr(exc.value, "code", "") == "SERIES_CODE_REQUIRED"
    assert store.dataset_counts()[bcb.DATASET] == 0


def test_dataset_tables_do_not_touch_the_b3_counts(store):
    sync.sync_dataset(tesouro.DATASET, _tesouro(
        "Tesouro Selic 2029;01/03/2029;01/11/2026;0,05;0,06;1;1;1"), store)
    assert store.count() == 0
    assert store.status()["quotes"] == 0


def test_an_unknown_dataset_has_no_table_and_is_refused(store):
    with pytest.raises(Exception) as exc:
        store.upsert_dataset("no_such_dataset", [])
    assert isinstance(exc.value, KeyError)
