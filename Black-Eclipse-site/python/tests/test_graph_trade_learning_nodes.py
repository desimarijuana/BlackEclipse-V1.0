"""The six trade-learning graph nodes: contracts, envelopes and execution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeExecContext
from harness.graph_runtime.trade_learning_nodes import (
    set_journal_loader,
    set_trade_learning_service,
)
from harness.persistence import AgentMemoryStore
from harness.trade_learning import TradeLearningService, TradeLearningStore

REGISTRY = build_default_registry()


def _context(node_type: str, *, inputs=None, config=None, test_run=False):
    definition = REGISTRY.get(node_type)
    assert definition is not None and definition.executor is not None
    return definition.executor(NodeExecContext(
        node_id=node_type, run_id="run", mode=ExecutionMode.PAPER,
        inputs=inputs or {}, config=config or {}, test_run=test_run,
        user_id="local",
    ))


def _trade(index: int, **overrides):
    payload = {
        "id": f"t{index}",
        "symbol": "EURUSD",
        "direction": "LONG",
        "entry": 1.10,
        "exit": 1.09,
        "stopLoss": 1.095,
        "takeProfit": 1.11,
        "quantity": 10_000,
        "entryTime": "2026-01-01T09:00:00+00:00",
        "exitTime": "2026-01-01T12:00:00+00:00",
        "status": "closed",
        "strategyId": "s1",
        "setupId": "setup1",
        "session": "London",
        "rMultiple": -1.0,
        "riskAmount": 100.0,
        "mfe": 0.4,
        "mae": -1.0,
        "actualRR": 2.0,
        "grade": "B",
    }
    payload.update(overrides)
    return payload


@pytest.fixture()
def service(tmp_path):
    store = TradeLearningStore(AgentMemoryStore(str(tmp_path / "am.db")))
    learning = TradeLearningService(store)
    set_trade_learning_service(learning)
    yield learning
    set_trade_learning_service(None)
    set_journal_loader(None)


MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "src" / "lib" / "graph-studio" / "registry.manifest.json"
)


def _manifest_nodes() -> dict[str, dict]:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        node["type"]: node for node in payload.get("nodes") or []
        if str(node.get("type", "")).startswith("trade.")
    }


def test_the_editor_and_runtime_agree_on_every_trade_node():
    """The cross-language contract, for this pack specifically.

    The generated manifest is the shared artefact. Ports, config names,
    defaults, capabilities, side effects and modes are compared directly; a
    drift here is a saved workflow the runtime cannot execute.
    """
    manifest = _manifest_nodes()
    python = {
        definition.type: definition
        for definition in REGISTRY.definitions()
        if definition.type.startswith("trade.")
    }
    assert set(python) == set(manifest)

    kind_map = {"integer": "number", "number": "number", "boolean": "boolean",
                "string": "string", "enum": "string", "object": "object",
                "array": "array"}

    for node_type, definition in python.items():
        node = manifest[node_type]
        assert [p.id for p in definition.inputs] == [p["id"] for p in node["inputs"]]
        assert [p.type.value for p in definition.inputs] == [p["type"] for p in node["inputs"]]
        assert [p.id for p in definition.outputs] == [p["id"] for p in node["outputs"]]
        assert [p.type.value for p in definition.outputs] == [p["type"] for p in node["outputs"]]

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
        assert sorted(mode.value for mode in definition.allowed_modes) == sorted(node["allowedModes"])


def test_every_trade_learning_node_is_registered_with_an_executor():
    for node_type in (
        "trade.journal", "trade.review", "trade.learn",
        "trade.improve", "trade.commit", "trade.playbook",
    ):
        definition = REGISTRY.get(node_type)
        assert definition is not None, node_type
        assert definition.executor is not None, node_type
        assert definition.category == "learning"


def test_journal_node_passes_wired_trades_through():
    result = _context("trade.journal", inputs={"trades": [_trade(1)]})
    assert result["trades"][0]["id"] == "t1"
    assert result["provenance"]["source"] == "wired"


def test_journal_node_fails_honestly_without_a_bridge():
    # Another test (or a booted service) may have bound the real loader; this
    # test is about the UNBOUND path, so it sets that precondition itself.
    set_journal_loader(None)
    set_trade_learning_service(None)
    with pytest.raises(ValueError, match="journal data bridge"):
        _context("trade.journal")


def test_review_node_is_pure_and_names_the_field():
    result = _context("trade.review", inputs={"trades": [_trade(1, stopLoss=None)]})
    assert [f["category"] for f in result["findings"]] == ["no_stop"]
    assert result["findings"][0]["evidence"] == {"stopLoss": None}
    assert result["summary"]["detectors"]


def test_learn_node_refuses_a_test_run(service):
    with pytest.raises(ValueError, match="operator run"):
        _context("trade.learn", inputs={"findings": []}, test_run=True)


def test_learn_node_records_and_reports_recurrence(service):
    findings = [
        {
            "tradeId": f"t{i}", "category": "no_stop", "severity": "high",
            "expected": "a stop", "actual": "none", "evidence": {"stopLoss": None},
            "signature": "sig-node", "detectorVersion": "1",
            "rMultiple": -1.0, "rAvailable": True, "symbol": "EURUSD",
        }
        for i in range(3)
    ]
    result = _context(
        "trade.learn", inputs={"findings": findings, "coverage": {"no_stop": {"fraction": 0.9}}},
    )
    assert result["recorded"] == 3
    assert result["recurring"][0]["windowCount"] == 3
    assert result["recurring"][0]["eligibility"] == "eligible"


def test_the_risk_gate_tightens_from_the_learned_envelope():
    from harness.graph_runtime.trading_nodes import _apply_learned_policy

    merged, enforced, not_enforced = _apply_learned_policy(
        {"requireStop": False, "maxRiskPerTradePct": 2.0},
        {"limits": {"requireStop": True, "riskPerTradePct": 0.5,
                    "symbolBlocklist": ["EURUSD"]}},
    )
    assert merged["requireStop"] is True
    assert merged["maxRiskPerTradePct"] == 0.5
    # The stateless gate can enforce a stop and a risk cap; it cannot enforce a
    # symbol list or a per-day count, and it says so.
    assert "symbolBlocklist" in not_enforced
    assert "requireStop" in enforced


def test_the_risk_gate_ignores_an_absent_envelope():
    from harness.graph_runtime.trading_nodes import _apply_learned_policy

    merged, enforced, not_enforced = _apply_learned_policy(
        {"requireStop": False, "maxRiskPerTradePct": 2.0}, None,
    )
    assert merged["requireStop"] is False
    assert merged["maxRiskPerTradePct"] == 2.0
    assert enforced == [] and not_enforced == []


def test_improve_node_proposes_and_commit_is_operator_only(service):
    trades = []
    for index in range(40):
        if index % 2 == 0:
            trades.append(_trade(index, stopLoss=None, rMultiple=-1.5, mfe=0.2,
                                 entryTime=f"2026-01-{(index % 27) + 1:02d}T09:00:00+00:00",
                                 exitTime=f"2026-01-{(index % 27) + 1:02d}T12:00:00+00:00"))
        else:
            trades.append(_trade(index, rMultiple=1.0, mfe=1.4,
                                 entryTime=f"2026-01-{(index % 27) + 1:02d}T13:00:00+00:00",
                                 exitTime=f"2026-01-{(index % 27) + 1:02d}T15:00:00+00:00"))
    bounds = json.dumps({"requireStop": {"allow": True}})
    improved = _context(
        "trade.improve",
        inputs={"trades": trades},
        config={"boundsJson": bounds, "k": 2, "generations": 1,
                "minValidationTrades": 5, "minLiftR": 0.01, "seed": 3},
    )
    assert improved["accepted"] is True
    assert improved["best"]["limits"]["requireStop"] is True

    committed = _context(
        "trade.commit",
        inputs={"candidate": improved["best"], "bounds": {"requireStop": {"allow": True}}},
    )
    assert committed["changed"] is True
    assert committed["playbook"]["version"] == 1

    with pytest.raises(ValueError, match="operator run"):
        _context(
            "trade.commit",
            inputs={"candidate": improved["best"]},
            test_run=True,
        )

    read = _context("trade.playbook", config={"includeHistory": True})
    assert read["playbook"]["version"] == 1
    assert len(read["versions"]) == 1
