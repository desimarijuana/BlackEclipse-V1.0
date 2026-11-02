"""Cross-language contract parity for the trading nodes.

The same node contract is declared twice: once in Python (the runtime that
executes it) and once in TypeScript (`registry-trading.ts`, the editor). The
generated `registry.manifest.json` is the shared artefact. A drift here is not a
cosmetic bug — a port the editor shows but the runtime does not accept turns into
a broken saved workflow, so the two declarations are compared directly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.graph_runtime.nodes import build_default_registry

MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "src" / "lib" / "graph-studio" / "registry.manifest.json"
)


def _manifest_nodes() -> dict[str, dict]:
    if not MANIFEST.exists():
        pytest.skip(f"{MANIFEST} is not built")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") or []
    return {
        node["type"]: node for node in nodes
        if str(node.get("type", "")).startswith("trading.")
    }


def _python_nodes() -> dict[str, object]:
    return {
        definition.type: definition
        for definition in build_default_registry().definitions()
        if definition.type.startswith("trading.")
    }


def test_every_python_trading_node_is_in_the_manifest_and_vice_versa():
    manifest = _manifest_nodes()
    python = _python_nodes()
    assert set(python) == set(manifest), (
        f"missing from manifest: {sorted(set(python) - set(manifest))}; "
        f"missing from python: {sorted(set(manifest) - set(python))}"
    )


@pytest.mark.parametrize("node_type", sorted(_python_nodes()))
def test_port_ids_and_side_effects_match(node_type):
    definition = _python_nodes()[node_type]
    manifest = _manifest_nodes()[node_type]

    assert [port.id for port in definition.inputs] == [
        port["id"] for port in manifest.get("inputs") or []
    ], f"{node_type} input ports drifted"
    assert [port.id for port in definition.outputs] == [
        port["id"] for port in manifest.get("outputs") or []
    ], f"{node_type} output ports drifted"

    assert definition.side_effects.value == manifest.get("sideEffects")
    assert sorted(mode.value for mode in definition.allowed_modes) == sorted(
        manifest.get("allowedModes") or []
    )
    assert sorted(definition.capabilities) == sorted(manifest.get("capabilities") or [])
