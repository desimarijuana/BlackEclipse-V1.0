"""Phase 9 G4 — the UNAVAILABLE path is exercised for every generated artefact.

Each generated artefact must return UNAVAILABLE (never a default or a synthetic
series) when its data is absent, and its generated test must prove it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from harness.code.kits import render_kit


def _load(tmp_path: Path, rel: str, text: str, module_name: str):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_ratio_unavailability_is_covered(tmp_path):
    rendered = render_kit("ratio_calculator", {"ratio_name": "roe", "description": "return on equity"})
    module = _load(tmp_path, "m/ratios_roe.py", rendered["python/harness/research/ratios_roe.py"], "kit_unav_roe")
    result = module.compute_ratio(numerator=1)
    assert result.status == "UNAVAILABLE" and result.value is None
    # The generated test proves the same branch.
    assert "UNAVAILABLE" in rendered["python/tests/test_ratios_roe.py"]


def test_backtest_unavailability_is_covered(tmp_path):
    rendered = render_kit("backtest_strategy", {"strategy_name": "mom", "period": "2020"})
    module = _load(
        tmp_path, "m/backtest_mom.py",
        rendered["python/harness/research/backtest_mom.py"], "kit_unav_mom",
    )
    result = module.run_backtest(None)
    assert result.status == "UNAVAILABLE" and result.metrics == {}
    assert "UNAVAILABLE" in rendered["python/tests/test_backtest_mom.py"]


def test_importer_skips_rather_than_fabricates(tmp_path):
    rendered = render_kit("data_ingestion_pipeline", {"source_name": "acme"})
    module = _load(tmp_path, "scripts/import_acme.py", rendered["scripts/import_acme.py"], "kit_unav_imp")
    state, result = module.ingest({}, [{"v": 1}])
    assert state == {} and result.skipped == 1


def test_indicator_unavailability_is_covered():
    rendered = render_kit("chart_indicator", {"indicator_name": "sma"})
    source = rendered["src/lib/chart/sma.ts"]
    assert "return [];" in source  # empty on too-short input, never a fabricated point
    assert "returns an empty series" in rendered["src/lib/chart/sma.test.ts"]
