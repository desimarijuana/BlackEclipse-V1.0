"""Chat capabilities around the ML engine: per-model tools, lifecycle, distillation.

The per-model tool must be callable by the chat agent (registered AND allowlisted),
the lifecycle must be a governed transition (audited), and the generative path must
never pretend to have trained when its optional stack is absent.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from harness.ml import service as S
from harness.ml import tools as MLT
from harness.ml.store import MLStore
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def env(tmp_path):
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rows = [{"a": float(i % 5), "b": float((i * 3) % 7),
                 "label": "up" if (i % 5) >= 2 else "down"} for i in range(160)]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "chatty", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "label", "task": "classification"},
        }, name="chatty"))
        run = asyncio.run(S.execute_experiment({
            "datasetId": built["datasetId"], "datasetVersion": built["version"],
            "modelFamily": "logistic", "split": {"method": "walk_forward", "nSplits": 3},
            "seed": 3, "registerModel": True, "name": "churn model",
        }))
        yield built, run["registered"]["modelId"]
    finally:
        S.set_ml_store(None)


# ── per-model tool ───────────────────────────────────────────────────────────


def test_a_registered_model_becomes_its_own_chat_tool(env) -> None:
    from harness.tools import ToolRegistry

    _built, model_id = env
    registry = ToolRegistry()
    MLT._MODEL_TOOL_REGISTRY = registry
    try:
        name = MLT.register_model_tool(model_id, "churn model", "classification")
        assert name == "ml_model_churn_model_predict"
        assert registry.get(name) is not None
        assert registry.get(name).dynamic is True
    finally:
        MLT._MODEL_TOOL_REGISTRY = None

    # idempotent: registering twice does not raise or duplicate
    MLT._MODEL_TOOL_REGISTRY = registry
    try:
        assert MLT.register_model_tool(model_id, "churn model", "classification") == name
    finally:
        MLT._MODEL_TOOL_REGISTRY = None


def test_the_per_model_tool_is_excluded_from_the_portable_manifest() -> None:
    from harness.public import export_tool_schemas
    from harness.tools import ToolDefinition, ToolRegistry

    registry = ToolRegistry()

    async def handler(args, ctx):  # pragma: no cover - not called here
        return "ok", {}

    registry.register(ToolDefinition(
        name="ml_model_demo_predict", description="d", input_schema={}, handler=handler,
        dynamic=True))
    names = {tool["name"] for tool in export_tool_schemas(registry)}
    assert "ml_model_demo_predict" not in names


def test_the_per_model_tool_predicts(env) -> None:
    _built, model_id = env
    tool_name = MLT.model_tool_name("churn model", model_id)
    handler = MLT._predict_handler(model_id, tool_name)
    text, payload = asyncio.run(handler({"features": [[1.0, 2.0], [4.0, 5.0]]}, None))
    assert payload["status"] == "ok"
    assert len(payload["pred"]) == 2
    assert "predicted 2 row(s)" in text


# ── lifecycle ────────────────────────────────────────────────────────────────


def test_the_model_lifecycle_is_a_recorded_transition(env) -> None:
    _built, model_id = env
    evaluated = S.transition_model(model_id, version="1.0.0", action="evaluate",
                                   actor="operator", reason="reviewed")
    assert evaluated["status"] == "evaluated"
    approved = S.transition_model(model_id, version="1.0.0", action="approve_research",
                                  actor="operator", reason="research")
    assert approved["status"] == "approved_research"

    version = S.get_model_version(model_id)
    actions = [event["action"] for event in version["approvals"]]
    assert "approve_research" in actions


def test_an_unknown_lifecycle_action_is_refused(env) -> None:
    _built, model_id = env
    with pytest.raises(Exception):
        S.transition_model(model_id, version="1.0.0", action="ship_it", actor="x")


# ── distillation + fine-tune recipe ──────────────────────────────────────────


def test_the_corpus_is_chat_jsonl_with_real_labels(env) -> None:
    built, _model = env
    corpus = S.build_training_corpus(built["datasetId"], built["version"], limit=50)
    lines = corpus["content"].splitlines()
    assert corpus["rows"] == len(lines) > 0
    first = json.loads(lines[0])
    assert first["messages"][0]["role"] == "user"
    assert "Predict `label`" in first["messages"][0]["content"]
    assert first["messages"][1]["content"] in ("up", "down")
    assert "not general instruction data" in corpus["note"]

    again = S.build_training_corpus(built["datasetId"], built["version"], limit=50)
    assert again["hash"] == corpus["hash"]


def test_incomplete_rows_are_skipped_not_filled(tmp_path) -> None:
    ml = MLStore(AgentMemoryStore(str(tmp_path / "am.db")), artifact_root=str(tmp_path / "art"))
    S.set_ml_store(ml)
    try:
        rows = [{"a": 1.0, "b": 2.0, "y": 1.0},
                {"a": None, "b": 2.0, "y": 1.0},
                {"a": 3.0, "b": 4.0, "y": None}]
        built = asyncio.run(S.build_dataset_version(None, {
            "name": "sparse", "source": "records", "records": rows,
            "featureNames": ["a", "b"],
            "target": {"kind": "column", "column": "y", "task": "regression"},
            "missingPolicy": "drop",
        }, name="sparse"))
        corpus = S.build_training_corpus(built["datasetId"], built["version"])
        assert corpus["rows"] == 1
    finally:
        S.set_ml_store(None)


def test_the_fine_tune_writes_a_runnable_recipe_even_without_the_stack(env, tmp_path) -> None:
    built, _model = env
    out = S.fine_tune_adapter({
        "datasetId": built["datasetId"], "datasetVersion": built["version"],
        "name": "demo-adapter", "limit": 40,
    })
    assert out["depsAvailable"] in (True, False)
    assert os.path.exists(out["corpus"])
    assert os.path.exists(out["recipe"]["script"])
    assert os.path.exists(out["recipe"]["readme"])
    assert os.path.exists(out["recipe"]["manifest"])
    assert out["trained"] is None
    assert "vLLM or Ollama" in out["serveHint"]


def test_training_without_the_stack_refuses_honestly(env) -> None:
    from harness.ml.llm import adapter_support

    available, _reason = adapter_support()
    if available:
        pytest.skip("the fine-tuning stack is installed; the refusal path cannot run")
    built, _model = env
    with pytest.raises(Exception) as exc:
        S.fine_tune_adapter({
            "datasetId": built["datasetId"], "datasetVersion": built["version"],
            "name": "no-deps", "train": True, "limit": 10,
        })
    assert "optional stack" in str(exc.value)
