"""Phase 9 acceptance test for the `portfolio_module` kit."""

from __future__ import annotations

from harness.code.kits import get_kit, render_kit

_INPUTS = {"module_name": "weight_analysis"}


def test_kit_declares_ts_outputs():
    kit = get_kit("portfolio_module")
    assert kit is not None
    assert set(kit.manifest.produces) == {
        "src/lib/portfolio/{{module_name}}.ts",
        "src/lib/portfolio/{{module_name}}.test.ts",
    }


def test_rendered_module_is_pure_and_empty_on_no_input():
    rendered = render_kit("portfolio_module", _INPUTS)
    source = rendered["src/lib/portfolio/weight_analysis.ts"]
    assert "export function WeightAnalysis(" in source
    assert "return { total: 0, contributions: [] };" in source
    assert "vitest" in rendered["src/lib/portfolio/weight_analysis.test.ts"]
