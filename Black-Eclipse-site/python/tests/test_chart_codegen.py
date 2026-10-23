"""Phase 21 — a chart spec becomes an editable, honest starting script.

The generated program is a STARTING POINT, not the canonical chart. These tests
pin the two promises that make it safe: the numbers travel as data (not source
text), and anything the template cannot reproduce is named instead of silently
drawn as something else.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from harness.charts.codegen import generate_source
from harness.charts.spec import ChartSpec
from harness.code import sandbox as sandbox_mod
from harness.code.execution import AnalysisRequest, interpreter_path, run_analysis


def _has_runner() -> bool:
    try:
        sandbox_mod.select_backend()
    except sandbox_mod.SandboxUnavailable:
        return False
    return bool(interpreter_path())


@pytest.mark.parametrize(
    "spec",
    [
        ChartSpec(kind="line", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
        ChartSpec(kind="area", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
        ChartSpec(kind="bar", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
        ChartSpec(kind="pie", labels=["a", "b"], values=[1, 2]),
        ChartSpec(kind="donut", labels=["a", "b"], values=[1, 2]),
        ChartSpec(kind="scatter", points=[{"x": 1, "y": 2}]),
        ChartSpec(kind="histogram", series=[{"name": "s", "data": [0.1, -0.2, 0.3]}]),
        ChartSpec(kind="candlestick", candles=[{"open": 1, "high": 2, "low": 0.5, "close": 1.5}]),
    ],
)
def test_simple_charts_generate_a_compilable_script(spec):
    source, unsupported = generate_source(spec)
    assert unsupported == []
    compile(source, "<generated-chart>", "exec")
    assert 'inputs.get("chart")' in source
    assert 'write_artifact("chart.png"' in source
    assert "result =" in source


def test_scene_marks_that_cannot_be_reproduced_are_named():
    spec = ChartSpec(
        kind="scene",
        panels=[{"marks": [
            {"type": "line", "name": "A", "y": [1, 2, 3]},
            {"type": "violin", "name": "B", "values": [1, 2, 3]},
        ]}],
    )
    source, unsupported = generate_source(spec)
    assert "violin" in unsupported
    compile(source, "<generated-scene>", "exec")


def test_an_unsupported_simple_kind_is_named_not_hidden():
    spec = ChartSpec(kind="heatmap", matrix=[[1, 0.2], [0.2, 1]])
    source, unsupported = generate_source(spec)
    assert unsupported == ["heatmap"]
    compile(source, "<generated-heatmap>", "exec")


def test_data_is_not_embedded_in_the_source():
    spec = ChartSpec(
        kind="line",
        categories=["a", "b", "c"],
        series=[{"name": "NAV", "data": [111.11, 222.22, 333.33]}],
    )
    source, _ = generate_source(spec)
    assert "111.11" not in source
    assert "222.22" not in source


@pytest.mark.skipif(not _has_runner(), reason="no isolation primitive")
def test_the_generated_program_actually_draws_a_png():
    """The starting script runs in the SAME sandbox a notebook cell uses."""
    spec = ChartSpec(
        kind="line",
        title="Editable line",
        categories=["a", "b", "c"],
        series=[{"name": "NAV", "data": [1, 2, 3]}],
    )
    source, _ = generate_source(spec)
    request = AnalysisRequest(
        source=source,
        inputs=[{"name": "chart", "kind": "json", "value": spec.to_dict()}],
        purpose="phase 21 codegen",
        extra_imports=("io", "matplotlib"),
        timeout_s=60,
    )
    out = Path(tempfile.mkdtemp(prefix="nb_codegen_"))
    result = run_analysis(request, output_dir=out)
    assert result.status == "ok", result.stderr
    assert any(ref.name == "chart.png" for ref in result.artifacts)
    assert (out / "chart.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
