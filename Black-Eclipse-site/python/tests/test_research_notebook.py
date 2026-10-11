"""Isolated research notebook tests (real sandbox execution)."""

from __future__ import annotations

import os
import tempfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant.dataset_store import DatasetStore
from harness.research.notebook import materialize_dataset, run_notebook


@pytest.fixture()
def store(tmp_path):
    mem = AgentMemoryStore(path=str(tmp_path / "am.db"))
    return DatasetStore(mem, artifact_root=str(tmp_path / "art"))


def _series():
    return {
        "AAPL": [
            {"timestamp": "2026-01-02T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 1.0, "volume": 10},
            {"timestamp": "2026-01-03T00:00:00Z", "open": 1, "high": 2, "low": 0.5, "close": 2.0, "volume": 20},
        ]
    }


def test_materialize_dataset(store, tmp_path):
    manifest = store.build_version(series=_series(), dataset_id="ds_nb")
    workdir = tempfile.mkdtemp(dir=str(tmp_path))
    path, rows = materialize_dataset(store, "ds_nb", manifest["version"], workdir)
    assert rows == 2
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
    assert "symbol,timestamp" in content.splitlines()[0]
    assert "AAPL" in content


def test_run_notebook_reads_dataset(store, tmp_path):
    manifest = store.build_version(series=_series(), dataset_id="ds_nb2")
    workdir = tempfile.mkdtemp(dir=str(tmp_path))
    path, _ = materialize_dataset(store, "ds_nb2", manifest["version"], workdir)
    code = (
        "import os, csv\n"
        "p = os.environ['ECLIPSE_DATASET_PATH']\n"
        "rows = list(csv.DictReader(open(p)))\n"
        "print('ROWS', len(rows))\n"
        "vals = [float(r['close']) for r in rows]\n"
        "print('MEAN', sum(vals)/len(vals))\n"
    )
    result = run_notebook(code, dataset_path=path, timeout_s=20)
    assert result["status"] == "OK", result
    assert "ROWS 2" in result["output"]
    assert "MEAN 1.5" in result["output"]


def test_run_notebook_strips_secrets_and_proxy(tmp_path):
    code = (
        "import os\n"
        "print('TOKEN', os.environ.get('HARNESS_CALLBACK_TOKEN'))\n"
        "print('PROXY', os.environ.get('HTTPS_PROXY'))\n"
    )
    result = run_notebook(code, dataset_path=None, timeout_s=20)
    assert result["status"] == "OK", result
    assert "TOKEN None" in result["output"]
    assert "PROXY None" in result["output"]


def test_run_notebook_bad_code_fails_honestly(tmp_path):
    result = run_notebook("raise SystemExit(3)", dataset_path=None, timeout_s=20)
    assert result["status"] == "FAILED"
    assert result["exitCode"] == 3
