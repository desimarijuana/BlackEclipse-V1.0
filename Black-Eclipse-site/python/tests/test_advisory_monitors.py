"""The proactive-monitor catalogue — data, validation and definition building."""

from __future__ import annotations

import pytest

from harness.advisory.monitors import (
    MONITORS,
    build_definition,
    get_monitor,
    list_monitors,
    monitor_issues,
)


def test_catalogue_is_sound():
    assert monitor_issues() == []


def test_the_four_monitors_are_present():
    assert set(MONITORS) == {
        "position_weight_breach", "tax_loss_harvest", "cash_buffer_watch",
        "concentration_watch",
    }
    assert len(list_monitors()) == 4


def test_build_definition_produces_an_off_condition_automation():
    definition = build_definition(
        "position_weight_breach",
        {"portfolio_id": "pf_1", "symbol": "AAPL", "threshold": 0.25},
    )
    assert definition.state == "disabled"
    assert definition.trigger.type == "condition"
    assert definition.trigger.condition is not None
    assert definition.trigger.condition.expression == "pf.pf_1.weight.AAPL > 0.25"
    assert definition.trigger.condition.edge is True
    assert definition.action.type == "run_agent"
    assert "AAPL" in definition.action.objective


def test_tax_loss_monitor_condition_uses_the_unrealized_field():
    definition = build_definition(
        "tax_loss_harvest",
        {"portfolio_id": "pf_9", "symbol": "TSLA", "threshold": -1000},
    )
    assert definition.condition.expression == "pf.pf_9.unrealized.TSLA < -1000"


def test_a_missing_parameter_is_refused():
    with pytest.raises(ValueError):
        build_definition("position_weight_breach", {"portfolio_id": "pf_1"})


def test_an_unknown_monitor_is_refused():
    with pytest.raises(ValueError):
        build_definition("nope", {})
    assert get_monitor("nope") is None
