"""The exported HTML report embeds figures and never fails without them."""

from __future__ import annotations

from harness.quant.report_export import render_experiment_html


def _artifact(**overrides):
    base = {
        "metrics": {"sharpe": 1.2, "maxDrawdown": -0.18},
        "equityCurve": [
            {"ts": "2024-01-01", "equity": 100_000 + i * 250} for i in range(20)
        ],
        "drawdownCurve": [
            {"ts": "2024-01-01", "drawdown": -0.01 * i} for i in range(20)
        ],
        "configuration": {},
        "warnings": [],
    }
    base.update(overrides)
    return base


def test_report_embeds_inline_png_figures():
    html = render_experiment_html({"id": "e1", "kind": "backtest"}, _artifact())
    assert "data:image/png;base64," in html
    assert "<figcaption>Equity curve</figcaption>" in html
    # The images are inline: no external file or JS dependency.
    assert "<script" not in html


def test_report_still_renders_when_no_figures_are_possible():
    html = render_experiment_html({"id": "e2", "kind": "backtest"}, _artifact(equityCurve=[], drawdownCurve=[]))
    assert "<h2>Metrics</h2>" in html
    assert "No figures were available" in html


def test_report_survives_a_figure_builder_failure(monkeypatch):
    from harness.quant import report_export

    def boom(*args, **kwargs):
        raise RuntimeError("renderer exploded")

    monkeypatch.setattr("harness.quant.visuals.build_figures", boom)
    html = report_export.render_experiment_html({"id": "e3", "kind": "backtest"}, _artifact())
    assert "Figures unavailable" in html
    assert "sharpe" in html
