"""Tests for the three capability closures: PDF without pypdfium2, persistent
visual memory, and image generation."""

from __future__ import annotations

import asyncio

import pytest

from harness.schemas import ModelSettings
from harness.tools import ToolContext, ToolRegistry
from harness.vision import documents as doc
from harness.vision import generate as gen
from harness.vision.contracts import Region, VisionResult, VisualObservation
from harness.vision.errors import VisionErrorClass
from harness.vision.tools import register_vision_tools


# ── PDF: stdlib backend (no pypdfium2) ──────────────────────────────────────────


def _text_pdf() -> bytes:
    content = b"BT /F1 18 Tf 50 700 Td (Revenue: 1000) Tj 0 -24 Td (Cost: 400) Tj ET"
    objs = [
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj",
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj",
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj",
        b"4 0 obj<</Length " + str(len(content)).encode() + b">>stream\n" + content + b"\nendstream endobj",
        b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj",
    ]
    return b"%PDF-1.4\n" + b"\n".join(objs) + b"\ntrailer<</Root 1 0 R>>\n%%EOF"


def test_pdf_available_always_true() -> None:
    assert doc.pdf_available() is True
    caps = doc.pdf_capabilities()
    assert caps["textExtraction"] is True


def test_stdlib_pdf_extracts_text(monkeypatch) -> None:
    monkeypatch.setattr(doc, "_pypdfium_available", lambda: False)
    pdf = _text_pdf()
    assert doc.page_count(pdf) == 1
    page = doc.extract_page_text(pdf)
    assert "Revenue: 1000" in page.text
    assert page.has_text_layer is True
    assert page.text_method == "stdlib"


def test_stdlib_pdf_renders(monkeypatch) -> None:
    monkeypatch.setattr(doc, "_pypdfium_available", lambda: False)
    decoded = doc.render_page(_text_pdf())
    assert decoded.width > 0 and decoded.height > 0
    assert decoded.mime_type == "image/png"


def test_stdlib_pdf_no_pillow_reports_honestly(monkeypatch) -> None:
    monkeypatch.setattr(doc, "_pypdfium_available", lambda: False)
    monkeypatch.setattr(doc, "_stdlib_raster_ok", lambda: False)
    page = doc.extract_page_text(_text_pdf())
    assert page.has_text_layer is True
    assert page.raster_method == "none"
    with pytest.raises(Exception) as exc:
        doc.render_page(_text_pdf())
    # The stdlib render path raises UNSUPPORTED_FORMAT when it cannot draw.
    assert "UNSUPPORTED_FORMAT" in str(exc.value) or exc.value.error_class is VisionErrorClass.UNSUPPORTED_FORMAT


# ── image generation ───────────────────────────────────────────────────────────


def test_generate_requires_capable_model() -> None:
    settings = ModelSettings(provider="anthropic", model="claude-4", api_key="x", base_url="http://x")
    with pytest.raises(Exception) as exc:
        asyncio.run(gen.generate_image(settings, "a cat"))
    assert exc.value.error_class is VisionErrorClass.NO_VISION_MODEL


def test_generate_rejects_empty_prompt() -> None:
    settings = ModelSettings(provider="openai", model="gpt-image-1", api_key="x", base_url="http://x")
    with pytest.raises(Exception) as exc:
        asyncio.run(gen.generate_image(settings, "  "))
    assert exc.value.error_class is VisionErrorClass.INVALID_INPUT


def test_generate_parses_b64_response(monkeypatch, tmp_workspace) -> None:
    import base64
    import io

    from PIL import Image

    settings = ModelSettings(provider="openai", model="gpt-image-1", api_key="x", base_url="http://x")
    # Force capability detection to see image_generation support.
    monkeypatch.setattr(gen, "_image_generation_supported", lambda s: (True, ""))

    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), (1, 2, 3)).save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode()

    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"data": [{"b64_json": b64, "revised_prompt": "a refined cat"}]}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    generated = asyncio.run(gen.generate_image(settings, "a cat"))
    assert generated.decoded.width == 16
    assert generated.revised_prompt == "a refined cat"
    assert generated.to_dict()["type"] == "generated_image"


def test_generate_classifies_http_errors(monkeypatch) -> None:
    settings = ModelSettings(provider="openai", model="gpt-image-1", api_key="x", base_url="http://x")
    monkeypatch.setattr(gen, "_image_generation_supported", lambda s: (True, ""))

    class FakeResponse:
        status_code = 429
        text = "slow down"

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(Exception) as exc:
        asyncio.run(gen.generate_image(settings, "a cat"))
    assert exc.value.error_class is VisionErrorClass.RATE_LIMIT


# ── persistent visual memory ────────────────────────────────────────────────────


def test_remember_visual_goes_through_the_gate(tmp_workspace) -> None:
    """A visual memory is persisted only via the decision gate, with a TTL for a
    sensitive frame and the asset id in structuredData (never the bytes)."""
    from harness.eclipse_memory.service import EclipseMemoryService
    from harness.vision.memory import remember_visual

    service = EclipseMemoryService()
    result = VisionResult(
        ok=True, mode="analyze", description="A confidential account balance",
        observations=[VisualObservation(text="Balance $42", region=Region(1, 2, 10, 4), confidence=0.9)],
        asset_id="img_secret", provenance={"source": "screenshot", "security": {"sensitive": True}},
        provider="openai", model="gpt-4o",
    )

    class Ctx:
        memory_service = service
        user_message = "remember this screenshot please"
        user_id = "u1"
        run_id = "r1"

    outcome = remember_visual(result, Ctx(), subject="ACME")
    # The gate may save or suggest; either way nothing unsafe is stored as a blob.
    stored = service.store.list_memories(scope_id="u1", include_inactive=True)
    if outcome.get("saved"):
        assert stored and stored[0].get("structuredData")
        assert "img_secret" in str(stored[0]["structuredData"])
        # A sensitive/ephemeral result carries an expiry.
        assert outcome.get("expiresAt")
    else:
        assert outcome.get("saved") is False
    service.store.close()


def test_remember_visual_rejects_failed_result(tmp_workspace) -> None:
    from harness.eclipse_memory.service import EclipseMemoryService
    from harness.vision.memory import remember_visual

    service = EclipseMemoryService()
    failed = VisionResult.failure(
        __import__("harness.vision.errors", fromlist=["VisionError"]).VisionError(
            VisionErrorClass.NO_VISION_MODEL, "no model"
        )
    )

    class Ctx:
        memory_service = service
        user_message = "remember"
        user_id = "u1"
        run_id = "r1"

    with pytest.raises(Exception) as exc:
        remember_visual(failed, Ctx())
    assert exc.value.error_class is VisionErrorClass.INVALID_INPUT
    service.store.close()


def test_vision_remember_tool_requires_result() -> None:
    registry = ToolRegistry()
    register_vision_tools(registry)
    ctx = ToolContext(run_id="r", log=lambda *_: None)
    result = asyncio.run(registry.execute("vision_remember", "c1", {}, ctx))
    assert result.ok is False
    assert result.error.code == "TOOL_VALIDATION_FAILED"


# ── image_generate is gated ─────────────────────────────────────────────────────


def test_image_generate_is_refused_without_an_authorizer() -> None:
    from harness.vision.tools import image_generate

    settings_result = asyncio.run(image_generate({"prompt": "a cat"}, ToolContext(run_id="r", log=lambda *_: None)))
    # Without model settings it is an honest failure, not a fabricated image.
    assert settings_result[1].get("ok") is not True


def test_image_generate_refused_by_registry_without_approval() -> None:
    registry = ToolRegistry()
    register_vision_tools(registry)
    ctx = ToolContext(run_id="r", log=lambda *_: None)
    result = asyncio.run(registry.execute("image_generate", "c1", {"prompt": "a cat"}, ctx))
    # A non-read tool with no effect authorizer is refused before it runs.
    assert result.ok is False
    assert result.error.code == "TOOL_FORBIDDEN"


# ── operational fixes: the TTL is real, and sensitive is decided pre-flight ────


def test_sensitive_asset_gets_a_ttl_and_is_swept(tmp_workspace) -> None:
    """A sensitive frame is stored WITH an expiry, and sweep_expired removes it."""
    from pathlib import Path

    from harness.persistence import AgentMemoryStore as Store
    from harness.vision.config import VisionConfig
    from harness.vision.image import decode_bytes
    from harness.vision.storage import VisionAssetStore
    from vision_helpers import png_bytes

    work = Path(tmp_workspace)
    store = Store(path=str(work / "mem.db"))
    assets = VisionAssetStore(store, cfg=VisionConfig(), storage_dir=work / "assets")
    decoded = decode_bytes(png_bytes(40, 40), source="t")
    # Store with an expiry in the PAST so the sweep must remove it.
    asset = assets.save(decoded, run_id="r1", expires_at="2000-01-01T00:00:00Z")
    assert assets.get(asset.asset_id) is not None
    assert Path(asset.storage_uri).exists()
    removed = assets.sweep_expired()
    assert removed == 1
    assert assets.get(asset.asset_id) is None
    assert not Path(asset.storage_uri).exists()
    store.close()


def test_preflight_scan_flags_a_real_secret_but_not_a_bare_word(monkeypatch) -> None:
    from harness.vision import security
    from harness.vision.image import decode_bytes
    from harness.vision import ocr as ocr_mod
    from vision_helpers import png_bytes

    decoded = decode_bytes(png_bytes(50, 50), source="t")

    class FakeSecret:
        text = "key sk-abcdefghijklmnop1234567890"
        engine = "fake"

    monkeypatch.setattr(ocr_mod, "ocr_available", lambda cfg=None: True)
    monkeypatch.setattr(ocr_mod, "run_ocr", lambda decoded, **kw: FakeSecret())
    scan = security.preflight_scan(decoded)
    # A real API-key shape is a strong signal -> sensitive.
    assert scan.sensitive is True

    class FakeChart:
        text = "Token price up 4%"
        engine = "fake"

    monkeypatch.setattr(ocr_mod, "run_ocr", lambda decoded, **kw: FakeChart())
    scan2 = security.preflight_scan(decoded)
    # A bare "Token" (a crypto chart) is NOT auto-flagged sensitive.
    assert scan2.sensitive is False


def test_preflight_scan_skipped_without_ocr(monkeypatch) -> None:
    from harness.vision import security
    from harness.vision.image import decode_bytes
    from harness.vision import ocr as ocr_mod
    from vision_helpers import png_bytes

    decoded = decode_bytes(png_bytes(20, 20), source="t")
    monkeypatch.setattr(ocr_mod, "ocr_available", lambda cfg=None: False)
    scan = security.preflight_scan(decoded)
    # No OCR engine → the scan is empty and says so; it never claims the frame
    # is clean.
    assert scan.sensitive is False
    assert any("pre-flight" in n or "OCR" in n for n in scan.notes)


def test_startup_maintenance_runs_the_vision_sweep() -> None:
    """The lifespan startup hook runs the vision asset sweep so a TTL is real."""
    from harness import service as service_module

    calls: list[int] = []
    inst = object.__new__(service_module.AgenticService)

    class _Memory:
        def run_retention_maintenance(self):
            return {"ok": True, "expired": 0}

    class _Assets:
        def sweep_expired(self):
            calls.append(1)
            return 3

    inst.memory = _Memory()
    inst.vision_assets = _Assets()
    result = inst.run_startup_maintenance()
    assert calls == [1]
    assert result["visionAssetSweep"] == {"removed": 3}


