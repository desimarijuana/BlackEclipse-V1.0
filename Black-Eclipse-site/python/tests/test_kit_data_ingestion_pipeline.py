"""Phase 9 acceptance test for the `data_ingestion_pipeline` kit."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from harness.code.kits import render_kit

_INPUTS = {"source_name": "acme_universe"}


def _load(tmp_path: Path, rendered: dict[str, str]):
    rel = "scripts/import_acme_universe.py"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered[rel], encoding="utf-8")
    spec = importlib.util.spec_from_file_location("kit_import_acme", target)
    module = importlib.util.module_from_spec(spec)
    sys.modules["kit_import_acme"] = module
    spec.loader.exec_module(module)
    return module


def test_importer_is_idempotent_and_never_fabricates(tmp_path):
    rendered = render_kit("data_ingestion_pipeline", _INPUTS)
    module = _load(tmp_path, rendered)
    rows = [{"id": "a", "v": 1}, {"id": "b", "v": 2}]
    state1, r1 = module.ingest({}, rows)
    assert r1.inserted == 2
    state2, r2 = module.ingest(state1, rows)
    assert state2 == state1 and r2.inserted == 0
    # A row missing its key is skipped, not invented.
    state3, r3 = module.ingest({}, [{"v": 99}])
    assert state3 == {} and r3.skipped == 1


def test_rendered_paths_are_within_the_declared_set():
    rendered = render_kit("data_ingestion_pipeline", _INPUTS)
    assert set(rendered) == {
        "scripts/import_acme_universe.py",
        "python/tests/test_import_acme_universe.py",
    }
