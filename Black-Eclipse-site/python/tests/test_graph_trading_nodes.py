"""Paper-trading safety: a pure risk gate, a PAPER-only execution adapter, and a
compiler that refuses live trading and any trading node in a test run."""

from __future__ import annotations

import pytest

from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext

REGISTRY = build_default_registry()


def _node(node_id, node_type, config=None):
    return {"id": node_id, "type": node_type, "version": "1.0.0", "config": config or {}, "layout": {"x": 0, "y": 0}}


def _edge(edge_id, source, source_handle, target, target_handle):
    return {"id": edge_id, "source": source, "sourceHandle": source_handle, "target": target, "targetHandle": target_handle}


def _ir(mode: str = "paper") -> WorkflowIR:
    return WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_trade", "name": "Paper trade",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            _node("trig", "trigger.manual"),
            _node("risk", "trading.risk_check", {"price": 100.0, "maxPositionPct": 10.0}),
            _node("order", "trading.paper_order", {"price": 100.0}),
            _node("out", "output.result"),
        ],
        "edges": [
            _edge("e1", "trig", "start", "risk", "intent"),
            _edge("e2", "risk", "intent", "order", "intent"),
            _edge("e3", "order", "fill", "out", "value"),
        ],
        "settings": {"executionMode": mode, "failFast": False, "maxConcurrency": 1, "timeoutMs": 0},
        "requiredCapabilities": ["trading.risk", "trading.paper"],
    })


def _exec(node_type: str, config: dict, inputs: dict):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.PAPER,
        inputs=inputs, config=config,
    ))


def _intent(**overrides):
    base = {"symbol": "TESTUSDT", "side": "buy", "quantity": 10.0}
    base.update(overrides)
    return base


def test_risk_check_caps_size_and_adjusts_the_intent():
    result = _exec(
        "trading.risk_check",
        {"equity": 10_000.0, "price": 100.0, "maxPositionPct": 10.0},
        {"intent": _intent(quantity=50.0)},
    )
    assert result["approved"] is True
    assert result["intent"]["quantity"] == pytest.approx(10.0)
    assert result["decision"]["adjustments"]


def test_risk_check_rejects_a_disabled_side_without_raising():
    result = _exec(
        "trading.risk_check",
        {"equity": 10_000.0, "price": 100.0, "allowShort": False},
        {"intent": _intent(side="sell")},
    )
    assert result["approved"] is False
    assert result["decision"]["quantity"] == 0.0
    assert "short" in result["decision"]["reasons"][0]


def test_paper_order_fills_with_slippage_and_commission():
    result = _exec(
        "trading.paper_order",
        {"price": 100.0, "commissionPct": 0.1, "slippagePct": 0.5},
        {"intent": _intent(quantity=10.0)},
    )
    assert result["status"] == "FILLED"
    fill = result["fill"]
    assert fill["mode"] == "paper"
    assert fill["price"] == pytest.approx(100.5)
    assert fill["commission"] == pytest.approx(1.005)
    assert fill["cashDelta"] == pytest.approx(-1006.005)
    assert "no broker" in fill["note"]


def test_paper_order_refuses_a_rejected_decision():
    result = _exec(
        "trading.paper_order",
        {"price": 100.0},
        {
            "intent": _intent(),
            "decision": {"allowed": False, "quantity": 0.0, "reasons": ["blocked"]},
        },
    )
    assert result["status"] == "REJECTED"
    assert result["fill"] is None
    assert result["reasons"] == ["blocked"]


def test_paper_order_needs_a_price_and_a_valid_intent():
    with pytest.raises(ValueError, match="price"):
        _exec("trading.paper_order", {}, {"intent": _intent()})
    with pytest.raises(ValueError, match="side"):
        _exec("trading.paper_order", {"price": 100.0}, {"intent": _intent(side="hold")})


def test_compiler_refuses_trading_in_a_test_run_and_allows_a_paper_grant():
    denied = compile_workflow(_ir(), REGISTRY, RunGrants(test_run=True))
    assert denied.executable is False
    assert any(d.code == "permission_denied" for d in denied.diagnostics)

    allowed = compile_workflow(_ir(), REGISTRY, RunGrants(
        test_run=False,
        granted_capabilities=frozenset({"trading.risk", "trading.paper"}),
        allow_trading=True,
    ))
    assert allowed.executable is True


def test_compiler_refuses_live_and_an_ungranted_paper_run():
    live = compile_workflow(_ir("live"), REGISTRY, RunGrants(
        test_run=False,
        granted_capabilities=frozenset({"trading.risk", "trading.paper"}),
        allow_trading=True,
    ))
    assert live.executable is False
    assert any(d.code == "live_trading_unavailable" for d in live.diagnostics)

    ungranted = compile_workflow(_ir(), REGISTRY, RunGrants(
        test_run=False,
        granted_capabilities=frozenset({"trading.risk", "trading.paper"}),
    ))
    assert ungranted.executable is False
    assert any(d.code == "permission_denied" for d in ungranted.diagnostics)
