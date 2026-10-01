"""Phase 9 acceptance test for the `backtest_strategy` kit."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from harness.code.kits import render_kit

_INPUTS = {"strategy_name": "momentum", "period": "2020-2024"}


def _load(tmp_path: Path, rendered: dict[str, str], rel: str, module_name: str):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered[rel], encoding="utf-8")
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_backtest_runs_and_labels_in_sample(tmp_path):
    rendered = render_kit("backtest_strategy", _INPUTS)
    module = _load(tmp_path, rendered, "python/harness/research/backtest_momentum.py", "kit_bt_momentum")
    ok = module.run_backtest([100, 110, 121])
    assert ok.status == "OK" and ok.inSample is True
    assert ok.inputs["prices"] == [100, 110, 121]


def test_backtest_is_unavailable_without_prices(tmp_path):
    rendered = render_kit("backtest_strategy", _INPUTS)
    module = _load(tmp_path, rendered, "python/harness/research/backtest_momentum.py", "kit_bt_momentum2")
    missing = module.run_backtest(None)
    assert missing.status == "UNAVAILABLE" and missing.metrics == {}
