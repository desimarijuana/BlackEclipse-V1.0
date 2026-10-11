"""Portable strategy bundle export/import + safety + tool integration."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import strategy as S
from harness.quant.bundle import (
    BUNDLE_FORMAT,
    MAX_BUNDLE_BYTES,
    build_manifest,
    bundle_to_bytes,
    export_bundle,
    import_bundle,
    read_bundle_bytes,
)
from harness.quant.errors import StrategyBundleError
from harness.quant.schema import spec_content_hash
from harness.quant.store import QuantStore
from harness.quant.tools import register_quant_tools
from harness.tools import ToolContext, ToolRegistry


def _spec():
    return S.parse_strategy({
        "strategy": {"id": "ema_pack", "name": "EMA Pack", "version": "1.0.0"},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_f", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_s", "type": "ema", "params": {"period": 20}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_above", "right": {"ref": "ema_s"}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": 90},
    })


@pytest.fixture()
def store(tmp_path) -> QuantStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStore(ams, artifact_root=str(tmp_path / "art"))


# ── Round-trip ───────────────────────────────────────────────────────────────

def test_bundle_roundtrip_preserves_ir():
    spec = _spec()
    bundle = export_bundle(spec, provenance={"source": "test"})
    assert bundle["manifest"]["format"] == BUNDLE_FORMAT
    assert bundle["manifest"]["contentHash"] == spec_content_hash(spec)

    raw = bundle_to_bytes(bundle)
    result = import_bundle(raw)
    assert result["spec"].to_dict() == spec.to_dict()
    assert result["contentHash"] == spec_content_hash(spec)
    assert result["schema"]["compatible"] is True
    assert not [i for i in result["issues"] if i.severity == "error"]
    assert result["warnings"] == []


def test_import_from_dict_form():
    spec = _spec()
    bundle = export_bundle(spec)
    result = import_bundle(bundle)
    assert result["spec"].id == "ema_pack"
    assert result["manifest"]["strategyVersion"] == "1.0.0"


# ── Safety ───────────────────────────────────────────────────────────────────

def test_hash_mismatch_warns_but_loads():
    bundle = export_bundle(_spec())
    bundle["strategy"]["name"] = "Tampered"
    result = import_bundle(bundle)
    assert any("hash mismatch" in w for w in result["warnings"])


def test_path_traversal_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({
            "format": BUNDLE_FORMAT, "bundleVersion": 1,
            "schemaVersion": "1.0.0"}))
        zf.writestr("strategy.json", json.dumps(_spec().to_dict()))
        zf.writestr("../evil.json", "{}")
    with pytest.raises(StrategyBundleError, match="unsafe member"):
        read_bundle_bytes(buf.getvalue())


def test_unknown_format_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "other", "bundleVersion": 1}))
        zf.writestr("strategy.json", json.dumps(_spec().to_dict()))
    with pytest.raises(StrategyBundleError, match="unknown bundle format"):
        read_bundle_bytes(buf.getvalue())


def test_missing_members_rejected():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": BUNDLE_FORMAT}))
    with pytest.raises(StrategyBundleError, match="manifest.json and strategy.json"):
        read_bundle_bytes(buf.getvalue())


def test_oversized_bundle_rejected():
    with pytest.raises(StrategyBundleError, match="over the"):
        read_bundle_bytes(b"x" * (MAX_BUNDLE_BYTES + 1))


def test_not_a_zip_rejected():
    with pytest.raises(StrategyBundleError, match="not a valid zip"):
        read_bundle_bytes(b"not a zip")


def test_newer_schema_rejected():
    bundle = export_bundle(_spec())
    bundle["manifest"]["schemaVersion"] = "2.0.0"
    with pytest.raises(StrategyBundleError, match="not loadable"):
        import_bundle(bundle)


# ── Tool integration ─────────────────────────────────────────────────────────

@pytest.fixture()
def env(tmp_path):
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    store = QuantStore(ams, artifact_root=str(tmp_path / "art"))
    store.save_strategy(_spec())
    registry = ToolRegistry()
    register_quant_tools(registry)
    ctx = ToolContext(run_id="t", log=lambda *a, **k: None, quant_store=store)
    return registry, ctx, store


async def _call(registry, ctx, name, args):
    return await registry.execute(name, f"c_{name}", args, ctx)


async def test_tools_export_then_import(env):
    registry, ctx, store = env
    r = await _call(registry, ctx, "export_strategy",
                    {"strategyId": "ema_pack", "includeBytes": True})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["manifest"]["strategyId"] == "ema_pack"
    encoded = r.data["bundleBase64"]

    # Import under a new id and persist.
    r2 = await _call(registry, ctx, "import_strategy",
                     {"bundleBase64": encoded, "save": False})
    assert r2.ok and r2.data["status"] == "OK", r2.text
    assert r2.data["strategy"]["id"] == "ema_pack"


async def test_tool_diff_strategy_versions(env):
    registry, ctx, store = env
    spec2 = _spec()
    d = spec2.to_dict()
    d["version"] = "1.1.0"
    d["position_sizing"]["value"] = 50
    store.save_strategy(S.parse_strategy(d))
    r = await _call(registry, ctx, "diff_strategy_versions",
                    {"strategyId": "ema_pack", "from": "1.0.0", "to": "1.1.0"})
    assert r.ok and r.data["status"] == "OK", r.text
    assert r.data["changeCount"] >= 1
    assert r.data["sameContent"] is False
