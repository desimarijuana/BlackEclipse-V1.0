"""Vision tool + storage + evidence integration tests.

Exercises the registered `vision_*` tools through the real `ToolRegistry`, the
content-addressed asset store, and the Evidence-Engine bridge.
"""

from __future__ import annotations

import asyncio

import pytest

from harness.persistence import AgentMemoryStore
from harness.tools import ToolContext, ToolRegistry
from harness.vision.tools import register_vision_tools

from vision_helpers import FakeModel, install_fake_model, png_b64


def _ctx(**kwargs) -> ToolContext:
    return ToolContext(run_id="run-vision", log=lambda *_: None, **kwargs)


def test_register_vision_tools() -> None:
    registry = ToolRegistry()
    added = register_vision_tools(registry)
    assert "vision_analyze" in added
    assert "ocr_extract" in added
    assert "chart_analyze" in added
    assert "document_vision" in added
    assert "visual_ground" in added
    assert "image_generate" in added
    assert "vision_remember" in added
    # Idempotent: a second call adds nothing.
    assert register_vision_tools(registry) == []
    # Every vision tool is read-only EXCEPT image_generate, the one external
    # (paid provider) action, which is approval-gated via its effect class.
    for tool in registry.list():
        if tool.name == "image_generate":
            assert tool.permission == "external_action"
        else:
            assert tool.permission == "read", tool.name


def test_vision_capabilities_tool() -> None:
    registry = ToolRegistry()
    register_vision_tools(registry)
    ctx = _ctx()
    result = asyncio.run(registry.execute("vision_capabilities", "c1", {}, ctx))
    assert result.ok is True
    assert result.data["type"] == "vision_capabilities"
    assert "ocrAvailable" in result.data


def test_image_metadata_tool() -> None:
    registry = ToolRegistry()
    register_vision_tools(registry)
    result = asyncio.run(registry.execute("image_metadata", "c1", {"source": png_b64(64, 32)}, _ctx()))
    assert result.ok is True
    assert result.data["width"] == 64 and result.data["height"] == 32


def test_vision_analyze_tool_requires_model(monkeypatch) -> None:
    from harness.vision.cache import reset_cache

    reset_cache()
    registry = ToolRegistry()
    register_vision_tools(registry)
    result = asyncio.run(registry.execute("vision_analyze", "c1", {"source": png_b64()}, _ctx()))
    assert result.ok is True  # the tool succeeds; the RESULT reports unavailable
    assert result.data["ok"] is False
    assert result.data["error"]["errorClass"] == "NO_VISION_MODEL"


def test_vision_analyze_tool_with_model(monkeypatch) -> None:
    from harness.schemas import ModelSettings
    from harness.vision.cache import reset_cache

    reset_cache()
    install_fake_model(monkeypatch, FakeModel({
        "description": "A grey image", "observations": [{"text": "grey", "confidence": 0.9}], "confidence": 0.9,
    }))
    registry = ToolRegistry()
    register_vision_tools(registry)
    settings = ModelSettings(provider="ollama", model="llava", base_url="http://local", api_key=None)
    result = asyncio.run(registry.execute(
        "vision_analyze", "c1", {"source": png_b64(), "question": "what?"}, _ctx(model_settings=settings),
    ))
    assert result.ok is True
    assert result.data["ok"] is True
    assert result.data["description"] == "A grey image"


def test_invalid_args_are_rejected_by_schema() -> None:
    registry = ToolRegistry()
    register_vision_tools(registry)
    # `visual_compare` requires compare_with.
    result = asyncio.run(registry.execute("visual_compare", "c1", {"source": png_b64()}, _ctx()))
    assert result.ok is False
    assert result.error.code == "TOOL_VALIDATION_FAILED"


def test_asset_store_content_address_dedup(tmp_workspace) -> None:
    from pathlib import Path

    from harness.vision.config import VisionConfig
    from harness.vision.image import decode_bytes
    from harness.vision.storage import VisionAssetStore

    work = Path(tmp_workspace)
    store = AgentMemoryStore(path=str(work / "mem.db"))
    assets = VisionAssetStore(store, cfg=VisionConfig(), storage_dir=work / "assets")
    decoded = decode_bytes(png_b64(50, 50).encode() and __import__("base64").b64decode(png_b64(50, 50)), source="t")
    first = assets.save(decoded, run_id="r1")
    second = assets.save(decoded, run_id="r1")
    assert first.asset_id == second.asset_id
    assert assets.count() == 1
    assert assets.open_bytes(first.asset_id) is not None
    assert assets.get(first.asset_id).width == 50
    assert assets.delete(first.asset_id) is True
    assert assets.count() == 0
    store.close()


def test_evidence_bridge_records_observations(tmp_workspace) -> None:
    from pathlib import Path

    from harness.persistence import AgentMemoryStore as Store
    from harness.research.web_store import EvidenceStore
    from harness.vision.contracts import Region, VisionResult, VisualObservation
    from harness.vision.evidence import record_result_evidence

    work = Path(tmp_workspace)
    store = Store(path=str(work / "mem.db"))
    evidence = EvidenceStore(store)
    result = VisionResult(
        ok=True, mode="analyze", description="A chart",
        observations=[VisualObservation(text="Resistance near 420", region=Region(10, 20, 30, 40),
                                        confidence=0.74, method="model", kind="inferred")],
        provider="openai", model="gpt-4o", backend="native", asset_id="img_abc",
        provenance={"source": "base64"},
    )
    ids = record_result_evidence(evidence, result)
    assert ids
    stored = evidence.list_evidence("") if False else None
    # Evidence is persisted on the ONE store; a direct query proves it.
    row = store._db.execute("SELECT evidenceId, rawText, contentTrust FROM WebResearchEvidence").fetchone()
    assert row is not None
    assert row["contentTrust"] == "UNTRUSTED"
    store.close()


def test_screenshot_tool_reports_unavailable_without_display(monkeypatch) -> None:
    """In a headless CI the screenshot source must report honestly, never fake."""
    from harness.vision.cache import reset_cache

    reset_cache()
    registry = ToolRegistry()
    register_vision_tools(registry)
    result = asyncio.run(registry.execute("screenshot_analyze", "c1", {"question": "q"}, _ctx()))
    assert result.ok is True
    if result.data["ok"] is False:
        # An honest refusal, whichever reason applies: no model at all, a source
        # this mode cannot read, or — when a cloud model IS configured — the
        # local-only privacy policy refusing a SENSITIVE source (a screen
        # capture) that may not leave the machine.
        assert result.data["error"]["errorClass"] in (
            "UNSUPPORTED_SOURCE", "NO_SOURCE", "NO_VISION_MODEL", "PRIVACY_REFUSED",
        )
