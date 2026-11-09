"""The typed-decision graph nodes: contracts, execution and the zero-config demo.

Two nodes, one capability. The demo is the important one: it must work with NO
provider key and NO network, while still going through the SAME request →
provider → confidence-policy → audit pipeline a real decision provider uses.

The tests bind a real `DecisionService` (rules provider + a temp audit store) so
they exercise the production path, and they assert the fail-closed contract:
nothing is guessed, an unavailable answer is explicit, and an answer is never
treated as an authorization.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.decisions.registry import DecisionRegistry
from harness.decisions.providers.rules import RuleProvider
from harness.decisions.service import DecisionService
from harness.decisions.store import DecisionStore
from harness.graph_runtime.decision_nodes import set_decision_service
from harness.graph_runtime.compiler import RunGrants, compile_workflow
from harness.graph_runtime.model import ExecutionMode, WorkflowIR
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.persistence import AgentMemoryStore

REGISTRY = build_default_registry()

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "src" / "lib" / "graph-studio" / "registry.manifest.json"
)


@pytest.fixture()
def decision_service(tmp_path):
    store = DecisionStore(AgentMemoryStore(str(tmp_path / "am.db")))
    service = DecisionService(store, registry=DecisionRegistry([RuleProvider()]))
    set_decision_service(service)
    yield service
    set_decision_service(None)


def _context(node_type: str, *, inputs=None, config=None, test_run=False, mode=None):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(
        NodeExecContext(
            node_id=node_type,
            run_id="run-decision",
            mode=mode or ExecutionMode.RESEARCH,
            inputs=inputs or {},
            config=config or {},
            test_run=test_run,
            user_id="local",
        )
    )


# ── registration ────────────────────────────────────────────────────────────


def test_both_decision_nodes_are_registered_in_the_decision_category():
    for node_type in ("decision.ask", "decision.demo"):
        definition = REGISTRY.get(node_type)
        assert definition is not None, node_type
        assert definition.executor is not None, node_type
        assert definition.category == "decision", node_type


def test_decision_nodes_have_no_authorizing_side_effect():
    # `ask` may call a provider; `demo` writes the local audit record. Neither
    # can trade, write outside the store, or reach the network directly.
    assert REGISTRY.get("decision.ask").side_effects.value == "model"
    assert REGISTRY.get("decision.demo").side_effects.value == "local_write"


def test_decision_nodes_compile_in_a_default_test_run():
    """A zero-config demo is only useful if the reduced test envelope runs it."""
    ir = WorkflowIR.model_validate({
        "irVersion": 1, "id": "wf_decision_demo", "name": "Decision demo",
        "meta": {"createdAt": "", "updatedAt": "", "tags": []},
        "nodes": [
            {"id": "trig", "type": "trigger.manual", "version": "1.0.0",
             "config": {}, "layout": {"x": 0, "y": 0}},
            {"id": "decide", "type": "decision.demo", "version": "1.0.0",
             "config": {"scenario": "risk_gate"}, "layout": {"x": 200, "y": 0}},
            {"id": "out", "type": "output.result", "version": "1.0.0",
             "config": {}, "layout": {"x": 400, "y": 0}},
        ],
        "edges": [
            {"id": "e1", "source": "trig", "sourceHandle": "start",
             "target": "decide", "targetHandle": "state"},
            {"id": "e2", "source": "decide", "sourceHandle": "answers",
             "target": "out", "targetHandle": "value"},
        ],
        "settings": {"executionMode": "research", "failFast": False,
                     "maxConcurrency": 2, "timeoutMs": 0},
        "requiredCapabilities": [],
    })
    plan = compile_workflow(ir, REGISTRY, RunGrants())
    assert "capability_denied" not in [d.code for d in plan.diagnostics]
    assert plan.executable is True


def test_the_editor_and_runtime_agree_on_every_decision_node():
    """The generated manifest is the shared cross-language artefact."""
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest = {
        node["type"]: node
        for node in payload.get("nodes") or []
        if str(node.get("type", "")).startswith("decision.")
    }
    python = {
        definition.type: definition
        for definition in REGISTRY.definitions()
        if definition.type.startswith("decision.")
    }
    assert set(python) == set(manifest) == {"decision.ask", "decision.demo"}

    kind_map = {
        "integer": "number", "number": "number", "boolean": "boolean",
        "string": "string", "enum": "string", "object": "object",
        "array": "array",
    }

    for node_type, definition in python.items():
        node = manifest[node_type]
        assert [p.id for p in definition.inputs] == [p["id"] for p in node["inputs"]]
        assert [p.type.value for p in definition.inputs] == [
            p["type"] for p in node["inputs"]
        ]
        assert [p.id for p in definition.outputs] == [p["id"] for p in node["outputs"]]
        assert [p.type.value for p in definition.outputs] == [
            p["type"] for p in node["outputs"]
        ]

        editor_fields = {field["name"]: field for field in node["configFields"]}
        assert set(editor_fields) == {field.name for field in definition.config_fields}
        for field in definition.config_fields:
            assert editor_fields[field.name]["kind"] == kind_map[field.kind], field.name
            assert editor_fields[field.name]["default"] == field.default, field.name
            constraints = editor_fields[field.name].get("constraints") or {}
            if field.minimum is not None:
                assert constraints.get("min") == field.minimum, field.name
            if field.maximum is not None:
                assert constraints.get("max") == field.maximum, field.name
            if field.max_length is not None:
                assert constraints.get("maxLength") == field.max_length, field.name
            if field.enum:
                assert constraints.get("enum") == list(field.enum), field.name

        assert definition.side_effects.value == node["sideEffects"]
        assert sorted(definition.capabilities) == sorted(node["capabilities"])
        assert sorted(mode.value for mode in definition.allowed_modes) == sorted(
            node["allowedModes"]
        )


# ── the demo ────────────────────────────────────────────────────────────────


def test_demo_risk_gate_answers_deterministically_and_records_audit(
    decision_service,
):
    result = _context("decision.demo", config={"scenario": "risk_gate"})

    assert result["scenario"] == "risk_gate"
    assert result["status"] == "answered"
    assert result["provider"] == "rules"
    assert result["recordId"]
    assert result["answers"]["margin_within_limit"]["noul"] == 1.0
    assert result["answers"]["drawdown_alert"]["noul"] == 0.0
    assert "answered via rules" in result["summary"]

    # The audit record really exists in the store (immutable trail, not a log).
    records = decision_service.store.list_records(owner_id="local")
    assert [record["id"] for record in records] == [result["recordId"]]
    assert records[0]["runId"] == "run-decision"
    assert records[0]["tool"] == "graph.decision.demo"
    assert records[0]["status"] == "answered"


def test_demo_route_ticket_returns_a_typed_choice(decision_service):
    result = _context("decision.demo", config={"scenario": "route_ticket"})

    assert result["status"] == "answered"
    assert result["answers"]["team"]["type"] == "choice"
    assert result["answers"]["team"]["choice"] == "billing"


def test_demo_wired_state_overrides_the_sample(decision_service):
    # Same scenario, different state: the rule now answers NO.
    result = _context(
        "decision.demo",
        config={"scenario": "risk_gate"},
        inputs={"state": {"marginRatio": 0.9, "drawdownPct": 2.0}},
    )
    assert result["answers"]["margin_within_limit"]["noul"] == 0.0
    assert result["answers"]["drawdown_alert"]["noul"] == 0.0


def test_demo_unknown_scenario_fails_loudly(decision_service):
    with pytest.raises(ValueError, match="unknown demo scenario"):
        _context("decision.demo", config={"scenario": "nope"})


def test_demo_without_a_bound_service_fails_honestly():
    set_decision_service(None)
    with pytest.raises(ValueError, match="decision layer is not available"):
        _context("decision.demo")


# ── decision.ask ────────────────────────────────────────────────────────────


def test_ask_uses_configured_state_and_question_template(decision_service):
    result = _context(
        "decision.ask",
        config={
            "stateJson": json.dumps({"marginRatio": 0.4}),
            "questionsJson": json.dumps(
                {
                    "is_risky": {
                        "type": "noul",
                        "instructions": "Is the margin ratio above 0.25?",
                        "rule": {"fact": "marginRatio", "op": "gte", "value": 0.25},
                    }
                }
            ),
        },
    )
    assert result["status"] == "answered"
    assert result["answers"]["is_risky"]["noul"] == 1.0
    assert result["recordId"]


def test_ask_wired_state_wins_over_configured_state(decision_service):
    result = _context(
        "decision.ask",
        inputs={"state": {"marginRatio": 0.1}},
        config={
            "stateJson": json.dumps({"marginRatio": 0.9}),
            "questionsJson": json.dumps(
                {
                    "is_risky": {
                        "type": "noul",
                        "instructions": "Is the margin ratio above 0.25?",
                        "rule": {"fact": "marginRatio", "op": "gte", "value": 0.25},
                    }
                }
            ),
        },
    )
    assert result["answers"]["is_risky"]["noul"] == 0.0


def test_ask_requires_a_state(decision_service):
    with pytest.raises(ValueError, match="decision.ask needs a state"):
        _context(
            "decision.ask",
            config={
                "questionsJson": json.dumps(
                    {
                        "is_risky": {
                            "type": "noul",
                            "instructions": "Is it risky?",
                            "rule": {"fact": "x", "op": "exists"},
                        }
                    }
                )
            },
        )


def test_ask_requires_a_question_template(decision_service):
    with pytest.raises(ValueError, match="decision.ask needs a question template"):
        _context("decision.ask", config={"stateJson": json.dumps({"x": 1})})


def test_ask_rejects_invalid_json_at_the_boundary(decision_service):
    with pytest.raises(ValueError, match="questionsJson must be valid JSON"):
        _context(
            "decision.ask",
            config={"stateJson": json.dumps({"x": 1}), "questionsJson": "{not json"},
        )


def test_ask_fails_closed_when_no_provider_can_answer(decision_service):
    # A question with no declared rule is NOT guessed by the rules provider; the
    # service reports `unavailable` with an explicit reason.
    result = _context(
        "decision.ask",
        config={
            "stateJson": json.dumps({"x": 1}),
            "questionsJson": json.dumps(
                {"is_risky": {"type": "noul", "instructions": "Is it risky?"}}
            ),
        },
    )
    assert result["status"] == "unavailable"
    assert result["answers"] == {}
    assert result["reason"]
    assert "unavailable" in result["summary"].lower()
