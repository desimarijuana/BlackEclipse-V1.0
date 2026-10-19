"""Two-mode (Compose/Engineer) classifier tests (Phase 6)."""

from __future__ import annotations

from harness.ui.catalog import UiCatalog
from harness.ui.mode import UiMode, classify_request
from harness.ui.model import UiComponentSpec


def _catalog() -> UiCatalog:
    return UiCatalog([UiComponentSpec(id="metric-card", display_name="Metric", category="metrics")])


def test_compose_for_layout_change():
    decision = classify_request("move the latency chart below the activity timeline and make it smaller", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert "ui_move_widget" in decision.suggested_tools


def test_engineer_for_new_component():
    decision = classify_request("create a new component that renders a 3d globe of trades", catalog=_catalog())
    assert decision.mode is UiMode.ENGINEER
    assert any("new" in r for r in decision.reasons)


def test_engineer_for_plugin_and_backend():
    assert classify_request("build a plugin with a new API endpoint", catalog=_catalog()).mode is UiMode.ENGINEER
    assert classify_request("add a database table and a migration", catalog=_catalog()).mode is UiMode.ENGINEER


def test_both_when_mixed():
    decision = classify_request("add a new component for the dashboard and then add a widget", catalog=_catalog())
    assert decision.mode is UiMode.BOTH
    assert "ui_add_widget" in decision.suggested_tools


def test_engineer_for_new_widget():
    # A widget the catalog does not have is a NEW capability, not a compose.
    assert classify_request("create a new widget that shows live swap spreads", catalog=_catalog()).mode is UiMode.ENGINEER


def test_new_page_of_existing_widgets_is_compose():
    # A new page built from registered widgets is authored via compose tools.
    decision = classify_request("make me a new page for the rates desk", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert "ui_add_widget" in decision.suggested_tools


def test_engineer_for_new_tool():
    assert classify_request("build a new tool that prices swaptions", catalog=_catalog()).mode is UiMode.ENGINEER


def test_restyling_an_existing_widget_is_compose():
    decision = classify_request("change the design of my widgets and restyle the dashboard", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE


def test_known_component_prefers_compose():
    decision = classify_request("put a metric-card at the top of the page", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert "metric-card" in decision.matched_components


def test_no_signal_defaults_to_compose():
    decision = classify_request("hello", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert decision.confidence <= 0.3


def test_empty_request():
    assert classify_request("", catalog=_catalog()).mode is UiMode.COMPOSE


# ── new-interaction signals (a recorded gap: "slider calculator" died silently) ─


def test_engineer_for_a_slider_calculator():
    # The catalog has no interactive input component, so this is a NEW capability.
    decision = classify_request("Make a small calculator I can drive with sliders", catalog=_catalog())
    assert decision.mode is UiMode.ENGINEER
    assert any("slider" in r or "calculator" in r for r in decision.reasons)


def test_engineer_for_an_input_form():
    assert classify_request("add a form with a number input for position size", catalog=_catalog()).mode is UiMode.ENGINEER


def test_interaction_signal_does_not_false_positive_on_performance():
    # "form" must not match inside "performance" — a dashboard restyle is compose.
    decision = classify_request("improve the performance of my trading dashboard", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE


# ── catalog witness (round 4, W0.1) ───────────────────────────────────────────


def test_named_capability_absent_from_catalog_escalates():
    # The recorded defect: a "world clock" classified Compose with no witness,
    # then `ui_start_engineering` refused as "nothing to engineer".
    decision = classify_request(
        "add a multi-zone world clock to my dashboard showing New York, Karachi and London",
        catalog=_catalog(),
    )
    assert decision.mode is UiMode.ENGINEER
    assert decision.capability_gap is True
    assert decision.matched_components == []
    assert "no registered component matches" in decision.reasons[0]


def test_generic_add_widget_stays_compose_without_a_witness():
    # "widget" is a UI shape, not a capability: the ordinary compose flow stays.
    decision = classify_request("add a widget to my dashboard", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert decision.capability_gap is False


def test_layout_without_a_catalog_witness_stays_compose():
    # The target is the existing page, so no component witness is required.
    decision = classify_request("move the latency chart below the timeline", catalog=_catalog())
    assert decision.mode is UiMode.COMPOSE
    assert decision.capability_gap is False


def test_named_capability_present_in_catalog_composes_with_a_witness():
    catalog = UiCatalog([
        UiComponentSpec(id="metric-card", display_name="Metric", category="metrics"),
        UiComponentSpec(id="pie-chart", display_name="Pie Chart", category="charts", tags=["charts"]),
    ])
    decision = classify_request("add a pie chart to the dashboard", catalog=catalog)
    assert decision.mode is UiMode.COMPOSE
    assert decision.capability_gap is False
    assert "pie-chart" in decision.matched_components


def test_no_catalog_never_invents_a_gap():
    # Without a catalog there is no basis for a gap; stay on the safe default.
    decision = classify_request("add a multi-zone world clock", catalog=None)
    assert decision.mode is UiMode.COMPOSE
    assert decision.capability_gap is False
