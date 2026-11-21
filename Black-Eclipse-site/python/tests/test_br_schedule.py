"""Scheduled registration for the Brazilian datasets: due logic + fetch wiring.

Every case runs offline: the opener is a fixture dict, and the "publisher" is
whatever bytes the test hands over. What is pinned:

  * a dataset that has never run is due;
  * a **failed** run does not count as fresh (a failure is a reason to retry);
  * a successful run inside its cadence is not due;
  * one unreachable publisher does not stop the others;
  * the CVM zip is unwrapped to its CSV member;
  * the loop is OFF unless `BE_BR_SYNC=1`.
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from harness.br_data import bcb, cvm, schedule, tesouro
from harness.br_data.store import BrStore

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)

CVM_HEADER = ("TP_FUNDO;CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;"
              "CAPTC_DIA;RESG_DIA;NR_COTST")
TESOURO_HEADER = ("Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;"
                  "Taxa Venda Manha;PU Compra Mania;PU Venda Mania;PU Base Mania")


def _cvm_zip() -> bytes:
    text = "\n".join([
        CVM_HEADER,
        "FI;00.000.000/0001-00;2026-11-19;1.000,00;12,5;1.000,00;10,00;4,00;100",
    ])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("inf_diario_fi_202611.csv", text.encode("latin-1"))
    return buffer.getvalue()


def _tesouro_csv() -> bytes:
    return "\n".join([
        TESOURO_HEADER,
        "Tesouro Selic 2029;01/03/2029;19/11/2026;0,05;0,06;15.000,00;14.999,00;15.000,00",
    ]).encode("utf-8")


def _bcb_json() -> bytes:
    return b'[{"data":"19/11/2026","valor":"5,4321"}]'


def _opener(url: str, timeout: float) -> bytes:
    if "cvm" in url.lower() or url.endswith(".zip"):
        return _cvm_zip()
    if "tesouro" in url.lower():
        return _tesouro_csv()
    return _bcb_json()


@pytest.fixture()
def store(tmp_path) -> BrStore:
    return BrStore(tmp_path / "br.db")


def _mark_ok(store: BrStore, label: str, when: datetime) -> None:
    run_id = store.start_run(label)
    store.finish_run(run_id, rows=1, inserted=1, updated=0, status="ok")
    # `finish_run` writes "now"; rewrite it to the timestamp under test.
    with store._connect() as conn:  # noqa: SLF001 - the store's own file
        conn.execute("UPDATE sync_runs SET finished_at=? WHERE id=?",
                     (when.isoformat(timespec="seconds"), run_id))
        conn.commit()


# -- due logic --------------------------------------------------------------


def test_a_dataset_that_has_never_run_is_due(store):
    due = schedule.due_datasets(store, NOW, series=())
    assert "cotahist" in due and cvm.DATASET in due and tesouro.DATASET in due


def test_a_recent_success_is_not_due(store):
    for label in ("cotahist", cvm.DATASET):
        _mark_ok(store, label, NOW - timedelta(hours=2))
    due = schedule.due_datasets(store, NOW, series=())
    assert "cotahist" not in due and cvm.DATASET not in due


def test_an_old_success_is_due_again(store):
    _mark_ok(store, "cotahist", NOW - timedelta(hours=25))
    assert "cotahist" in schedule.due_datasets(store, NOW, series=())


def test_a_failed_run_does_not_count_as_fresh(store):
    run_id = store.start_run(tesouro.DATASET)
    store.finish_run(run_id, rows=0, inserted=0, updated=0, status="failed",
                     error="HTTP_503")
    assert tesouro.DATASET in schedule.due_datasets(store, NOW, series=())


def test_each_bcb_series_is_scheduled_separately(store):
    _mark_ok(store, f"{bcb.DATASET}:1", NOW - timedelta(hours=1))
    due = schedule.due_datasets(store, NOW, series=(1, 432))
    assert f"{bcb.DATASET}:1" not in due
    assert f"{bcb.DATASET}:432" in due


# -- fetching ---------------------------------------------------------------


THREE = {cvm.DATASET: {"every_hours": 24}, bcb.DATASET: {"every_hours": 24},
         tesouro.DATASET: {"every_hours": 24}}


def test_sync_due_fetches_each_dataset_and_records_counts(store, tmp_path):
    outcomes = schedule.sync_due(store, dest_dir=tmp_path, opener=_opener, now=NOW,
                                 series=(1,), schedules=THREE)
    by_label = {o["dataset"]: o for o in outcomes}
    assert by_label[cvm.DATASET]["status"] == "ok"
    assert by_label[cvm.DATASET]["inserted"] == 1
    assert by_label[tesouro.DATASET]["inserted"] == 1
    assert by_label[f"{bcb.DATASET}:1"]["inserted"] == 1
    counts = store.dataset_counts()
    assert counts[cvm.DATASET] == 1
    assert counts[tesouro.DATASET] == 1
    assert counts[bcb.DATASET] == 1


def test_a_second_pass_inside_the_cadence_does_nothing(store, tmp_path):
    schedule.sync_due(store, dest_dir=tmp_path, opener=_opener, now=NOW,
                      series=(1,), schedules=THREE)
    again = schedule.sync_due(store, dest_dir=tmp_path, opener=_opener,
                              now=NOW + timedelta(hours=1), series=(1,),
                              schedules=THREE)
    assert again == []


def test_one_failure_does_not_stop_the_others(store, tmp_path):
    def flaky(url: str, timeout: float) -> bytes:
        if "tesouro" in url.lower():
            raise RuntimeError("publisher down")
        return _opener(url, timeout)

    outcomes = schedule.sync_due(store, dest_dir=tmp_path, opener=flaky, now=NOW,
                                 series=(1,), schedules=THREE)
    by_label = {o["dataset"]: o for o in outcomes}
    assert by_label[tesouro.DATASET]["status"] == "failed"
    assert "publisher down" in by_label[tesouro.DATASET]["error"]
    # The others still synced.
    assert by_label[cvm.DATASET]["status"] == "ok"
    assert by_label[f"{bcb.DATASET}:1"]["status"] == "ok"


def test_a_missing_series_code_is_reported_not_raised(store, tmp_path):
    outcomes = schedule.sync_due(store, dest_dir=tmp_path, opener=_opener, now=NOW,
                                 series=(), schedules={bcb.DATASET: {"every_hours": 24}})
    # No series planned, so nothing is attempted for BCB at all.
    assert all(o["dataset"] != bcb.DATASET for o in outcomes)


# -- the loop ---------------------------------------------------------------


def test_the_loop_is_off_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("BE_BR_SYNC", raising=False)
    assert schedule.br_sync_enabled() is False
    assert schedule.start_br_sync(object()) is None
    monkeypatch.setenv("BE_BR_SYNC", "0")
    assert schedule.br_sync_enabled() is False
    monkeypatch.setenv("BE_BR_SYNC", "1")
    assert schedule.br_sync_enabled() is True


def test_enabling_registers_a_task_that_can_be_stopped(tmp_path, monkeypatch):
    monkeypatch.setenv("BE_BR_SYNC", "1")
    monkeypatch.setattr(schedule, "sync_due", lambda *a, **k: [])

    class _Service:
        data_dir = str(tmp_path)

    async def scenario():
        task = schedule.start_br_sync(_Service())
        assert task is not None and not task.done()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


def test_the_loop_survives_a_failing_pass(tmp_path, monkeypatch):
    calls: list = []
    stop = asyncio.Event()

    def boom(*a, **k):
        calls.append(1)
        raise RuntimeError("network gone")

    monkeypatch.setattr(schedule, "sync_due", boom)

    async def scenario():
        task = asyncio.create_task(
            schedule.sync_loop(BrStore(tmp_path / "x.db"), interval_s=0.01, stop=stop)
        )
        for _ in range(50):
            await asyncio.sleep(0.01)
            if calls:
                break
        stop.set()
        await asyncio.wait_for(task, timeout=2)

    asyncio.run(scenario())
    assert calls            # it tried, failed, and did not die
