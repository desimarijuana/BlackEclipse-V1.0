"""Market-structure nodes: alignment, regime labels and position sizing.

All three are adapters over tested engines, so the tests pin the adapter's own
contracts: which shapes are accepted, that gaps stay visible, that warm-up bars
are never labelled, and that an uncomputable size fails by name.
"""

from __future__ import annotations

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.quant import fixtures as F

REGISTRY = build_default_registry()


def _run(node_type: str, inputs: dict, config: dict | None = None) -> dict:
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type,
        run_id="run",
        mode=ExecutionMode.RESEARCH,
        inputs=inputs,
        config=config or {},
    ))


# ── quant.align ─────────────────────────────────────────────────────────────


def test_align_uses_the_shared_timestamps_for_an_inner_join():
    a = F.bull_market("AAA", n=10)
    b = F.bull_market("BBB", n=10)[2:8]
    result = _run(
        "quant.align",
        {"series": {"AAA": a, "BBB": {"rows": b}}},
        {"join": "inner", "column": "close"},
    )
    aligned = result["aligned"]
    assert aligned["symbols"] == ["AAA", "BBB"]
    assert len(aligned["timestamps"]) == 6
    assert aligned["series"]["AAA"][0] == a[2]["close"]
    assert result["metadata"]["missing"] == {"AAA": 0, "BBB": 0}
    assert result["metadata"]["imputed"] is False


def test_align_keeps_gaps_null_by_default_and_counts_them():
    a = F.bull_market("AAA", n=10)
    b = F.bull_market("BBB", n=10)[2:8]
    result = _run(
        "quant.align",
        {"series": {"AAA": a, "BBB": b}},
        {"join": "outer", "column": "close", "fill": "none"},
    )
    aligned = result["aligned"]
    assert len(aligned["timestamps"]) == 10
    assert result["metadata"]["missing"] == {"AAA": 0, "BBB": 4}
    assert aligned["series"]["BBB"][0] is None


def test_align_imputes_only_when_asked_and_still_records_it():
    a = F.bull_market("AAA", n=10)
    b = F.bull_market("BBB", n=10)[2:8]
    result = _run(
        "quant.align",
        {"series": {"AAA": a, "BBB": b}},
        {"join": "outer", "fill": "zero"},
    )
    aligned = result["aligned"]
    assert aligned["series"]["BBB"][0] == 0.0
    assert result["metadata"]["imputed"] is True
    # With a fill, the gap is imputed rather than left null: the flag says so.
    assert result["metadata"]["missing"] == {"AAA": 0, "BBB": 0}


def test_align_rejects_a_single_payload_instead_of_guessing():
    a = {"symbol": "AAA", "rows": F.bull_market("AAA", n=5)}
    with pytest.raises(ValueError, match="map of"):
        _run("quant.align", {"series": a})
    with pytest.raises(ValueError, match="mapping each symbol"):
        _run("quant.align", {"series": {}})
    with pytest.raises(ValueError, match="no OHLCV rows"):
        _run("quant.align", {"series": {"AAA": []}})


# ── quant.regime ────────────────────────────────────────────────────────────


def test_regime_labels_every_bar_and_keeps_warmup_uninformed():
    series = {"symbol": "TESTUSDT", "interval": "1d", "rows": F.bull_market("TESTUSDT", n=220)}
    result = _run("quant.regime", {"series": series})
    regimes = result["regimes"]["TESTUSDT"]
    assert len(regimes["labels"]) == 220
    warmup = regimes["warmupBars"]
    assert warmup > 0
    # The trend filter has no reading during warm-up: those bars are `flat`.
    assert set(regimes["trend"][:warmup]) == {"flat"}
    assert sum(regimes["counts"].values()) == 220
    assert regimes["axes"]["trend"] == ["up", "down", "flat"]
    assert result["summary"].startswith("TESTUSDT")


def test_regime_refuses_a_series_without_a_symbol():
    rows = F.bull_market("TESTUSDT", n=220)
    with pytest.raises(ValueError, match="symbol"):
        _run("quant.regime", {"series": {"interval": "1d", "rows": rows}})


def test_regime_rejects_an_invalid_classifier_config():
    series = {"symbol": "TESTUSDT", "interval": "1d", "rows": F.bull_market("TESTUSDT", n=220)}
    with pytest.raises(ValueError, match="regime classification failed"):
        _run("quant.regime", {"series": series}, {"fast": 60, "slow": 20})


# ── quant.position_size ─────────────────────────────────────────────────────


def test_percent_equity_size_is_the_engine_quantity():
    result = _run(
        "quant.position_size",
        {"price": 100.0},
        {"method": "percent_equity", "value": 10, "equity": 100_000, "maxFraction": 1},
    )
    assert result["quantity"] == pytest.approx(100.0)
    assert result["size"]["notional"] == pytest.approx(10_000.0)
    assert result["size"]["method"] == "percent_equity"


def test_percent_risk_size_uses_the_stop_distance():
    result = _run(
        "quant.position_size",
        {"price": 100.0, "stop": 5.0},
        {"method": "percent_risk", "value": 1, "equity": 100_000, "maxFraction": 1},
    )
    # 1% of 100k = 1,000 risk / 5.0 stop distance = 200 units.
    assert result["quantity"] == pytest.approx(200.0)


def test_atr_sizing_uses_the_wired_atr():
    result = _run(
        "quant.position_size",
        {"price": 50.0, "atr": 2.0},
        {"method": "atr", "value": 2, "equity": 100_000, "atrMultiplier": 1, "maxFraction": 1},
    )
    # 2% of 100k = 2,000 risk / (2.0 ATR × 1) = 1,000 units.
    assert result["quantity"] == pytest.approx(1_000.0)


def test_lot_size_rounds_the_quantity_down_to_the_increment():
    result = _run(
        "quant.position_size",
        {"price": 100.0, "stop": 7.0},
        {"method": "percent_risk", "value": 1, "equity": 100_000, "lotSize": 10},
    )
    # 1,000 risk / 7.0 = 142.857 units, floored to a 10-unit lot = 140.
    assert result["quantity"] == pytest.approx(140.0)
    assert result["size"]["notional"] == pytest.approx(14_000.0)


def test_a_size_below_the_venue_minimum_is_zero_with_a_reason():
    result = _run(
        "quant.position_size",
        {"price": 100.0},
        {"method": "fixed_quantity", "value": 1, "minQuantity": 5},
    )
    assert result["quantity"] == 0.0
    assert "minimum" in result["size"]["reason"]


def test_a_missing_required_input_fails_by_name():
    with pytest.raises(ValueError, match="stop distance"):
        _run(
            "quant.position_size",
            {"price": 100.0},
            {"method": "percent_risk", "value": 1},
        )
    with pytest.raises(ValueError, match="ATR"):
        _run(
            "quant.position_size",
            {"price": 100.0},
            {"method": "atr", "value": 1},
        )
    with pytest.raises(ValueError, match="price"):
        _run("quant.position_size", {}, {})
