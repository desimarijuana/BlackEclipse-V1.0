"""Single-node test surface: one executor, explicit inputs, safe envelope.

`GraphService.test_node` is the editor's "Test node" action. These tests prove
it runs exactly one node, validates the contract, enforces required inputs and
refuses side-effecting nodes — without ever creating a run row.
"""

from __future__ import annotations

import pytest

from harness.graph_runtime.service import GraphService, NodeTestError


def _service() -> GraphService:
    # test_node never touches the run store; a real service supplies one.
    return GraphService(store=None)  # type: ignore[arg-type]


def test_zero_config_trigger_emits_null_without_a_run_input():
    result = _service().test_node(
        node_type="trigger.manual",
        version="1.0.0",
        config={},
        inputs={},
    )
    assert result["ok"] is True
    assert result["node"]["type"] == "trigger.manual"
    assert result["outputs"] == {"start": None}
    assert result["durationMs"] >= 0


def test_pure_node_runs_with_explicit_inputs():
    result = _service().test_node(
        node_type="transform.formula",
        version="1.0.0",
        config={"expression": "x * 2"},
        inputs={"x": 3},
    )
    assert result["outputs"] == {"result": 6.0}


def test_missing_required_input_is_reported():
    with pytest.raises(NodeTestError) as exc:
        _service().test_node(
            node_type="transform.formula",
            version="1.0.0",
            config={"expression": "x"},
            inputs={},
        )
    assert exc.value.status_code == 400
    assert "Missing required input" in exc.value.message


def test_invalid_input_type_is_reported():
    with pytest.raises(NodeTestError) as exc:
        _service().test_node(
            node_type="transform.formula",
            version="1.0.0",
            config={"expression": "x"},
            inputs={"x": "not a number"},
        )
    assert exc.value.status_code == 400
    assert 'input "x"' in exc.value.message


def test_side_effecting_node_is_refused_by_the_safe_envelope():
    with pytest.raises(NodeTestError) as exc:
        _service().test_node(
            node_type="integration.http",
            version="1.0.0",
            config={"url": "https://example.com"},
            inputs={},
        )
    assert exc.value.status_code == 403
    assert "safe envelope" in exc.value.message


def test_unknown_node_type_is_a_404():
    with pytest.raises(NodeTestError) as exc:
        _service().test_node(node_type="nope.nope", version="1.0.0", config={}, inputs={})
    assert exc.value.status_code == 404
