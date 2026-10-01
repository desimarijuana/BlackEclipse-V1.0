"""Phase 9 acceptance test for the `chart_indicator` kit.

The generated output is TypeScript; this test checks the rendered source has the
pure-function shape and the empty-on-short-input rule (the real vitest gate is run
by the scaffold tool in a worktree, not here).
"""

from __future__ import annotations

from harness.code.kits import get_kit, render_kit

_INPUTS = {"indicator_name": "moving_average"}


def test_kit_declares_ts_outputs():
    kit = get_kit("chart_indicator")
    assert kit is not None
    assert set(kit.manifest.produces) == {
        "src/lib/chart/{{module_name}}.ts",
        "src/lib/chart/{{module_name}}.test.ts",
    }


def test_rendered_indicator_is_pure_and_empty_on_short_input():
    rendered = render_kit("chart_indicator", _INPUTS)
    source = rendered["src/lib/chart/moving_average.ts"]
    assert "export function MovingAverage(" in source
    assert "return [];" in source  # empty on too-short input, never a fabricated point
    test_source = rendered["src/lib/chart/moving_average.test.ts"]
    assert "vitest" in test_source
