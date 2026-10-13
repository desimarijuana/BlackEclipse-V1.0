"""Internet image search: contract normalization, validation, collection, tools.

Covers the deterministic parts (no live network): the shared `ImageSearchResult`
contract, the run collector, and the `image_search` / `validate_image_result` /
`render_image_gallery` tools driven by a fake bridge.
"""

from __future__ import annotations

from typing import Any

import pytest

from harness.research import web_tools
from harness.research.image_contracts import (
    ImageCollector,
    normalize_image,
    normalize_images,
    validate_image_result,
)
from harness.tools import ToolContext


def _ctx(bridge: Any, sink: Any = None) -> ToolContext:
    return ToolContext(run_id="r", log=lambda m, d=None: None, data_bridge=bridge, image_sink=sink)


# ── contract ────────────────────────────────────────────────────────────────


def test_normalize_image_accepts_https_and_preserves_attribution():
    result = normalize_image(
        {
            "imageUrl": "https://cdn.example.com/h100.jpg",
            "thumbnailUrl": "https://cdn.example.com/h100-t.jpg",
            "sourceUrl": "https://example.com/h100",
            "title": "H100 GPU",
            "width": 1200,
            "height": 800,
            "attribution": "by NVIDIA (CC0)",
        }
    )
    assert result is not None
    assert result["imageUrl"] == "https://cdn.example.com/h100.jpg"
    assert result["sourceDomain"] == "example.com"
    assert result["width"] == 1200
    assert result["attribution"].startswith("by NVIDIA")
    assert result["validationStatus"] == "metadata_ok"


def test_normalize_image_rejects_unsafe_or_missing_urls():
    assert normalize_image({"imageUrl": "javascript:alert(1)"}) is None
    assert normalize_image({"imageUrl": "http://127.0.0.1/secret.png"}) is None
    assert normalize_image({"imageUrl": "http://10.0.0.5/x.png"}) is None
    assert normalize_image({"title": "no url"}) is None
    assert normalize_image("https://x.com/a.png") is None


def test_normalize_images_dedupes_and_bounds():
    images = normalize_images(
        [
            {"imageUrl": "https://a.com/x.jpg"},
            {"imageUrl": "https://a.com/x.jpg"},
            {"imageUrl": "https://a.com/y.jpg"},
            {"imageUrl": "javascript:alert(1)"},
        ]
    )
    assert [i["imageUrl"] for i in images] == ["https://a.com/x.jpg", "https://a.com/y.jpg"]


def test_validate_image_result_flags_non_image_mime_and_incomplete_dims():
    bad = validate_image_result({"imageUrl": "https://a.com/x.bin", "mimeType": "application/pdf"})
    assert bad["ok"] is False and bad["status"] == "rejected"
    partial = validate_image_result({"imageUrl": "https://a.com/x.jpg", "width": 100})
    assert partial["ok"] is False and "incomplete dimensions" in partial["reasons"]
    good = validate_image_result({"imageUrl": "https://a.com/x.jpg", "width": 100, "height": 50})
    assert good["ok"] is True and good["result"]["validationStatus"] == "metadata_ok"
    assert validate_image_result({"imageUrl": "javascript:1"})["status"] == "rejected"


def test_image_collector_blob_is_deduped_and_empty_when_no_results():
    collector = ImageCollector()
    assert collector.to_blob() is None
    collector.add([{"imageUrl": "https://a.com/x.jpg"}, {"imageUrl": "https://a.com/x.jpg"}])
    collector.add({"images": [{"imageUrl": "https://a.com/y.jpg"}]})
    blob = collector.to_blob()
    assert blob["status"] == "collected"
    assert blob["count"] == 2
    assert blob["schemaVersion"] == "1.0"


# ── tools ───────────────────────────────────────────────────────────────────


class _ImageBridge:
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        assert capability == "image_search"
        return {
            "status": "OK",
            "provider": "openverse",
            "images": [
                {"imageUrl": "https://cdn.example.com/a.jpg", "sourceUrl": "https://example.com/a", "title": "A"},
                {"imageUrl": "https://cdn.example.com/b.jpg", "title": "B"},
            ],
            "diagnostics": [],
        }


class _MissingBridge:
    async def fetch(self, capability: str, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "UNAVAILABLE",
            "failureClass": "not_configured",
            "error": "no image-search provider is configured",
            "images": [],
            "diagnostics": [],
        }


@pytest.mark.asyncio
async def test_image_search_collects_validated_images():
    collected: list[Any] = []
    ctx = _ctx(_ImageBridge(), sink=collected.append)
    text, payload = await web_tools.image_search({"query": "NVIDIA H100"}, ctx)
    assert payload["status"] == "OK"
    assert payload["count"] == 2
    assert all(img["imageUrl"].startswith("https://") for img in payload["images"])
    assert collected, "validated images should reach the collector"
    assert len(collected[0]) == 2


@pytest.mark.asyncio
async def test_image_search_reports_missing_config_honestly():
    collected: list[Any] = []
    ctx = _ctx(_MissingBridge(), sink=collected.append)
    text, payload = await web_tools.image_search({"query": "anything"}, ctx)
    assert payload["status"] == "UNAVAILABLE"
    assert payload["images"] == []
    assert "not_configured" in payload.get("error", "") or payload.get("error")
    assert collected == []  # never fabricate a gallery from a failure


@pytest.mark.asyncio
async def test_render_image_gallery_rejects_unsafe_candidates():
    ctx = _ctx(_MissingBridge())
    text, payload = await web_tools.render_image_gallery(
        {"images": [{"imageUrl": "javascript:alert(1)"}]}, ctx
    )
    assert payload["status"] == "REJECTED"
    assert payload["images"] == []


@pytest.mark.asyncio
async def test_validate_image_tool_rejects_and_accepts():
    ctx = _ctx(_MissingBridge())
    _, rejected = await web_tools.validate_image({"image_url": "javascript:alert(1)"}, ctx)
    assert rejected["status"] == "REJECTED"
    _, ok = await web_tools.validate_image({"image_url": "https://a.com/x.jpg", "width": 10, "height": 10}, ctx)
    assert ok["status"] == "OK"
