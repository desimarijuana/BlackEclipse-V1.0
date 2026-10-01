"""Phase 9 acceptance test for the `ratio_calculator` kit.

The kit's own rule: a generated ratio computes from explicit inputs AND returns
UNAVAILABLE (never a default) when an input is absent. This renders the kit,
imports the generated module, and proves both branches.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from harness.code.kits import get_kit, render_kit
from harness.code.kits.loader import KitLoadError

_INPUTS = {"ratio_name": "gross_margin", "description": "(revenue - cogs) / revenue"}


def _load_generated(tmp_path: Path, rel: str, text: str, module_name: str):
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(module_name, target)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_kit_loads_and_produces_only_declared_files():
    kit = get_kit("ratio_calculator")
    assert kit is not None
    rendered = render_kit("ratio_calculator", _INPUTS)
    assert set(rendered) == set(kit.manifest.produces) or set(rendered) == {
        "python/harness/research/ratios_gross_margin.py",
        "python/tests/test_ratios_gross_margin.py",
    }


def test_generated_ratio_computes_and_is_unavailable_without_inputs(tmp_path):
    rendered = render_kit("ratio_calculator", _INPUTS)
    module = _load_generated(
        tmp_path, "python/harness/research/ratios_gross_margin.py",
        rendered["python/harness/research/ratios_gross_margin.py"], "ratios_gross_margin",
    )
    ok = module.compute_ratio(numerator=80, denominator=100)
    assert ok.status == "OK" and ok.value == 0.8
    missing = module.compute_ratio(numerator=80)
    assert missing.status == "UNAVAILABLE" and missing.value is None
    assert missing.formula  # explains itself


def test_missing_required_input_is_refused_at_render():
    import pytest

    with pytest.raises(KitLoadError) as info:
        render_kit("ratio_calculator", {"ratio_name": "gross_margin"})
    assert info.value.code == "KIT_INPUT_MISSING"


def test_unknown_input_is_refused_at_render():
    import pytest

    with pytest.raises(KitLoadError) as info:
        render_kit("ratio_calculator", {**_INPUTS, "bogus": 1})
    assert info.value.code == "KIT_INPUT_INVALID"


def test_invalid_identifier_is_refused_at_render():
    import pytest

    with pytest.raises(KitLoadError) as info:
        render_kit("ratio_calculator", {"ratio_name": "Not A Slug", "description": "x"})
    assert info.value.code == "KIT_INPUT_INVALID"
