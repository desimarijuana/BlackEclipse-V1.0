"""The chart engine — the spec contract, the renderer and the tool.

The rules under test:
  * a spec is DATA — it carries no code, and a spec that does not satisfy its
    kind is refused with the missing part named;
  * the renderer draws what the spec says and nothing else;
  * a figure is always `computed`, never evidence (ADR-H123);
  * a missing matplotlib is an honest refusal, never a blank picture.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.charts.render import (
    CHART_RENDER_UNAVAILABLE,
    CHART_SPEC_INVALID,
    ChartRenderError,
    render_chart,
)
from harness.charts.service import render_spec, spec_digest
from harness.charts.spec import ChartSpec
from harness.charts.tools import chart_schema, python_chart, register_chart_tools
from harness.tools import ToolContext, ToolRegistry


def _ctx(**overrides) -> ToolContext:
    base = dict(
        run_id="run_chart",
        log=lambda *_: None,
        user_id="local",
        model_settings=None,
        tool_registry=ToolRegistry(),
        memory_store=None,
    )
    base.update(overrides)
    return ToolContext(**base)


# ── The spec contract ───────────────────────────────────────────────────────


def test_a_line_chart_needs_a_series():
    with pytest.raises(Exception):
        ChartSpec(kind="line", title="empty")


def test_a_pie_chart_needs_one_label_per_value():
    with pytest.raises(Exception):
        ChartSpec(kind="pie", labels=["a", "b"], values=[1, 2, 3])


def test_a_heatmap_needs_rectangular_rows():
    with pytest.raises(Exception):
        ChartSpec(kind="heatmap", matrix=[[1, 2], [3]])


def test_a_spec_carries_no_code():
    """The spec is data: an extra field is refused, never executed."""
    with pytest.raises(Exception):
        ChartSpec(kind="line", series=[{"name": "a", "data": [1]}], callback="print(1)")


def test_a_spec_refuses_an_unknown_kind():
    with pytest.raises(Exception):
        ChartSpec(kind="sunburst")


def test_the_spec_digest_is_stable_and_content_addressed():
    a = ChartSpec(kind="line", series=[{"name": "a", "data": [1, 2]}])
    b = ChartSpec(kind="line", series=[{"name": "a", "data": [1, 2]}])
    c = ChartSpec(kind="line", series=[{"name": "a", "data": [1, 3]}])
    assert spec_digest(a) == spec_digest(b)
    assert spec_digest(a) != spec_digest(c)


# ── The renderer ────────────────────────────────────────────────────────────


def test_a_line_chart_renders_a_png():
    spec = ChartSpec(
        kind="line",
        title="Equity curve",
        categories=["Jan", "Feb", "Mar"],
        series=[{"name": "NAV", "data": [100, 104, 101]}],
    )
    png = render_chart(spec)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 1_000


@pytest.mark.parametrize(
    "spec",
    [
        ChartSpec(kind="bar", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
        ChartSpec(kind="stackedBar", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
        ChartSpec(kind="pie", labels=["a", "b"], values=[1, 2]),
        ChartSpec(kind="donut", labels=["a", "b"], values=[1, 2]),
        ChartSpec(kind="scatter", points=[{"x": 1, "y": 2}]),
        ChartSpec(kind="histogram", series=[{"name": "s", "data": [0.1, -0.2, 0.3]}]),
        ChartSpec(kind="heatmap", matrix=[[1, 0.2], [0.2, 1]]),
        ChartSpec(kind="candlestick", candles=[{"open": 1, "high": 2, "low": 0.5, "close": 1.5}]),
        ChartSpec(kind="waterfall", series=[{"name": "s", "data": [3, -1]}]),
        ChartSpec(kind="radar", labels=["a", "b"], values=[1, 2]),
        ChartSpec(kind="area", categories=["a", "b"], series=[{"name": "s", "data": [1, 2]}]),
    ],
)
def test_every_chart_kind_draws(spec):
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_missing_reading_is_a_gap_not_a_zero():
    """A `None` is a missing reading; drawing it as 0 would invent data."""
    spec = ChartSpec(
        kind="line",
        categories=["a", "b", "c"],
        series=[{"name": "s", "data": [1, None, 3]}],
    )
    assert render_chart(spec)[:8] == b"\x89PNG\r\n\x1a\n"


def test_a_chart_with_no_values_is_refused():
    spec = ChartSpec(kind="line", series=[{"name": "s", "data": []}])
    with pytest.raises(ChartRenderError) as excinfo:
        render_chart(spec)
    assert excinfo.value.code == CHART_SPEC_INVALID


def test_a_missing_matplotlib_is_an_honest_refusal(monkeypatch):
    import harness.charts.render as render_module

    def _boom():
        raise ChartRenderError(CHART_RENDER_UNAVAILABLE, "matplotlib is not installed")

    monkeypatch.setattr(render_module, "_pyplot", _boom)
    spec = ChartSpec(kind="line", series=[{"name": "s", "data": [1, 2]}])
    with pytest.raises(ChartRenderError) as excinfo:
        render_module.render_chart(spec)
    assert excinfo.value.code == CHART_RENDER_UNAVAILABLE


# ── The service ─────────────────────────────────────────────────────────────


def test_the_figure_is_labelled_computed_and_never_evidence():
    spec = ChartSpec(kind="line", title="t", series=[{"name": "s", "data": [1, 2]}])
    rendered = render_spec(spec)
    figure = rendered.to_dict()
    assert figure["label"] == "computed"
    assert figure["isEvidence"] is False
    assert figure["sha256"] == rendered.sha256


# ── The tool ────────────────────────────────────────────────────────────────


def test_the_tool_is_registered():
    registry = ToolRegistry()
    register_chart_tools(registry)
    assert registry.get("python_chart") is not None


def test_the_schema_is_well_formed():
    schema = chart_schema()
    assert schema["type"] == "object"
    assert schema["required"] == ["kind"]
    assert "series" in schema["properties"]


def test_a_malformed_spec_is_refused_with_the_missing_part():
    text, data = asyncio.run(python_chart({"kind": "pie", "labels": ["a"], "values": [1, 2]}, _ctx()))
    assert data["status"] == "refused"
    assert data["code"] == CHART_SPEC_INVALID
    assert "REFUSED" in text


def test_the_tool_draws_and_reports_a_computed_figure():
    text, data = asyncio.run(python_chart(
        {
            "kind": "line",
            "title": "Equity curve",
            "categories": ["Jan", "Feb"],
            "series": [{"name": "NAV", "data": [100, 104]}],
        },
        _ctx(),
    ))
    assert data["status"] == "ok"
    assert data["figure"]["isEvidence"] is False
    assert data["figure"]["label"] == "computed"
    # The text never claims the chart is a source.
    assert "not a source" in text
