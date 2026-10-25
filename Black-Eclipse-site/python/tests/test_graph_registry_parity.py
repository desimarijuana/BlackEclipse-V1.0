"""TS↔Python node registry parity.

The editor registry (`src/lib/graph-studio/registry.ts`) and the runtime registry
(`harness/graph_runtime/nodes.py`) are separate code on purpose: one drives the
palette, the other authorizes execution. They must still describe the SAME
contracts. `registry.manifest.json` is generated from the TS side
(`npm run graph:manifest`); this suite proves the Python side agrees node for
node.

If this fails, change BOTH registries and regenerate the manifest. Never relax
the assertion: a silent mismatch means a graph the editor accepts is rejected by
the runtime (or worse, has different ports).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.nodes import build_default_registry
from harness.graph_runtime.registry import NodeDef, NodeExecContext

MANIFEST_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "lib" / "graph-studio" / "registry.manifest.json"
)


def _load_ts_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _port(port: Any) -> dict[str, Any]:
    return {
        "id": port.id,
        "name": port.name,
        "type": port.type.value,
        "kind": port.kind.value,
        "optional": port.optional,
        "nullable": port.nullable,
    }


def _python_node(definition: NodeDef) -> dict[str, Any]:
    return {
        "type": definition.type,
        "version": definition.version,
        "category": definition.category,
        "label": definition.label,
        "inputs": [_port(port) for port in definition.inputs],
        "outputs": [_port(port) for port in definition.outputs],
        "configFields": sorted(field.name for field in definition.config_fields),
        "capabilities": sorted(definition.capabilities),
        "sideEffects": definition.side_effects.value,
        "allowedModes": sorted(mode.value for mode in definition.allowed_modes),
        "terminal": definition.terminal,
    }


def _ts_node(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": node["type"],
        "version": node["version"],
        "category": node["category"],
        "label": node["label"],
        "inputs": node["inputs"],
        "outputs": node["outputs"],
        "configFields": sorted(field["name"] for field in node["configFields"]),
        "capabilities": sorted(node["capabilities"]),
        "sideEffects": node["sideEffects"],
        "allowedModes": sorted(node["allowedModes"]),
        "terminal": node["terminal"],
    }


def test_python_registry_matches_the_ts_manifest():
    manifest = _load_ts_manifest()
    ts_nodes = {
        f"{node['type']}@{node['version']}": _ts_node(node)
        for node in manifest["nodes"]
    }
    registry = build_default_registry()
    py_nodes = {
        f"{definition.type}@{definition.version}": _python_node(definition)
        for definition in registry.definitions()
    }

    assert set(py_nodes) == set(ts_nodes), (
        f"missing in Python: {sorted(set(ts_nodes) - set(py_nodes))}; "
        f"missing in TS: {sorted(set(py_nodes) - set(ts_nodes))}"
    )
    for key in sorted(ts_nodes):
        assert py_nodes[key] == ts_nodes[key], key


def test_set_variables_merges_configured_over_input():
    definition = build_default_registry().get("data.set_variables")
    assert definition is not None
    assert definition.executor is not None
    result = definition.executor(
        NodeExecContext(
            node_id="vars",
            run_id="run",
            mode=ExecutionMode.RESEARCH,
            inputs={"in": {"a": 1, "b": 2}},
            config={"variables": {"b": 3, "c": 4}},
        )
    )
    assert result == {"variables": {"a": 1, "b": 3, "c": 4}}


def test_set_variables_rejects_a_non_object_input():
    definition = build_default_registry().get("data.set_variables")
    assert definition is not None and definition.executor is not None
    try:
        definition.executor(
            NodeExecContext(
                node_id="vars",
                run_id="run",
                mode=ExecutionMode.RESEARCH,
                inputs={"in": ["not", "an", "object"]},
                config={},
            )
        )
    except ValueError as exc:
        assert "object" in str(exc)
    else:  # pragma: no cover - the assertion above is the point
        raise AssertionError("expected a ValueError for a non-object input")
