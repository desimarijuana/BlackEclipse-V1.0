"""Vision-read image nodes (no rendering, no generation)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from harness.graph_runtime.image_nodes import (
    exec_image_analyze,
    exec_image_attach,
    exec_image_batch,
    exec_image_compare,
    exec_image_ocr,
    exec_image_read_chart,
    set_vision_asset_store,
    set_vision_runner,
)
from harness.graph_runtime.model import ExecutionMode
from harness.graph_runtime.registry import NodeExecContext


def _asset(asset_id: str, name: str = "a.png") -> SimpleNamespace:
    return SimpleNamespace(
        asset_id=asset_id, mime_type="image/png", width=640, height=480,
        byte_size=1_024, sha256="abc", source_ref=name, metadata={"name": name},
    )


class FakeStore:
    def __init__(self) -> None:
        self.assets = {item.asset_id: item for item in (_asset("img_a"), _asset("img_b", "b.png"))}

    def get(self, asset_id: str):
        return self.assets.get(asset_id)

    def open_bytes(self, asset_id: str) -> bytes:
        return b"\x89PNG\r\n\x1a\n" if asset_id in self.assets else b""


@pytest.fixture()
def vision(monkeypatch):
    store = FakeStore()
    set_vision_asset_store(store)
    calls: list[dict] = []

    def runner(context, request):
        calls.append(request)
        mode = request["mode"]
        if mode == "ocr":
            return {
                "ok": True, "mode": "ocr", "description": "BUY 100",
                "text": [{"text": "BUY", "bounds": {"x": 0, "y": 0, "width": 10, "height": 5}}],
                "provider": None, "model": None, "backend": "ocr:tesseract",
                "confidence": 0.9, "warnings": [], "provenance": {},
            }
        if mode == "chart":
            return {
                "ok": True, "mode": "chart", "description": "uptrend",
                "chart": {
                    "trend": "up", "patterns": ["bull flag"],
                    "verification": {"available": bool(request["options"].get("symbol"))},
                },
                "provider": "p", "model": "m", "backend": "model",
                "confidence": 0.8, "warnings": [], "provenance": {},
            }
        if mode == "compare":
            return {
                "ok": True, "mode": "compare", "description": "wick changed",
                "comparison": {
                    "changed": True, "changedPixelsRatio": 0.1,
                    "regions": [{"x": 1, "y": 2, "width": 3, "height": 4}],
                    "confidence": 0.7, "warnings": [],
                },
                "provider": "p", "model": "m", "backend": "pixel+model",
                "confidence": 0.7, "warnings": [], "provenance": {},
            }
        structured = {"answer": "bullish"} if request["question"] else {}
        if "Schema" in request["question"]:
            structured = {"pattern": "hammer", "confidence": 0.9}
        return {
            "ok": True, "mode": mode, "description": "a chart with candles",
            "observations": [{"text": "bullish engulfing", "confidence": 0.9}],
            "structured": structured,
            "provider": "p", "model": "m", "backend": "model",
            "confidence": 0.85, "warnings": [], "provenance": {},
        }

    set_vision_runner(runner)
    try:
        yield calls
    finally:
        set_vision_asset_store(None)
        set_vision_runner(None)


def _ctx(config=None, inputs=None, *, test_run=False):
    return NodeExecContext(
        node_id="image", run_id="run", mode=ExecutionMode.RESEARCH,
        inputs=inputs or {}, config=config or {}, test_run=test_run,
    )


def test_attach_returns_image_meta(vision):
    result = exec_image_attach(_ctx({"assetId": "img_a"}))
    assert result["image"]["assetId"] == "img_a"
    assert result["image"]["width"] == 640


def test_attach_missing_image_fails_by_name(vision):
    with pytest.raises(ValueError, match="does not exist"):
        exec_image_attach(_ctx({"assetId": "img_missing"}))


def test_analyze_describe_marks_the_result_as_an_observation(vision):
    result = exec_image_analyze(_ctx({"assetId": "img_a", "mode": "describe"}))
    assert result["description"]
    assert result["meta"]["kind"] == "observation"
    assert result["meta"]["verified"] is False
    assert result["meta"]["provider"] == "p"


def test_analyze_answer_requires_a_question(vision):
    with pytest.raises(ValueError, match="needs a question"):
        exec_image_analyze(_ctx({"assetId": "img_a", "mode": "answer"}))


def test_analyze_extract_validates_the_schema(vision):
    result = exec_image_analyze(_ctx({
        "assetId": "img_a", "mode": "extract",
        "schemaJson": '{"type":"object","required":["pattern"],"properties":{"pattern":{"type":"string"}}}',
    }))
    assert result["data"]["pattern"] == "hammer"
    assert "schemaIssues" not in result["meta"]


def test_analyze_extract_schema_mismatch_is_null_with_issues(vision):
    result = exec_image_analyze(_ctx({
        "assetId": "img_a", "mode": "extract",
        "schemaJson": '{"type":"object","required":["missing"],"properties":{"missing":{"type":"string"}}}',
    }))
    assert result["data"] is None
    assert "schemaIssues" in result["meta"]


def test_ocr_returns_text_and_spans(vision):
    result = exec_image_ocr(_ctx({"assetId": "img_a"}))
    assert result["text"] == "BUY 100"
    assert result["spans"][0]["text"] == "BUY"


def test_read_chart_verified_only_with_a_market_check(vision):
    unverified = exec_image_read_chart(_ctx({"assetId": "img_a"}))
    assert unverified["verified"] is False
    assert unverified["reading"]["trend"] == "up"
    verified = exec_image_read_chart(_ctx({"assetId": "img_a", "symbol": "AAPL"}))
    assert verified["verified"] is True


def test_compare_returns_pixel_similarity(vision):
    result = exec_image_compare(_ctx({"assetId": "img_a", "compareAssetId": "img_b"}))
    assert result["same"] is False
    assert result["score"] == pytest.approx(0.9)
    assert result["meta"]["compareWith"] == "img_b"


def test_batch_reads_each_image_and_reports_a_failed_row(vision):
    result = exec_image_batch(_ctx({
        "assetIds": '["img_a","img_missing","img_b"]',
        "questionsJson": '["Describe the candles."]',
    }))
    assert result["summary"]["images"] == 3
    assert result["summary"]["succeeded"] == 2
    assert result["summary"]["failed"] == 1
    assert result["results"][1]["ok"] is False
    assert result["results"][0]["name"] == "a.png"


def test_batch_requires_questions(vision):
    with pytest.raises(ValueError, match="at least one question"):
        exec_image_batch(_ctx({"assetIds": '["img_a"]'}))


def test_test_run_can_read_an_image(vision):
    result = exec_image_analyze(_ctx({"assetId": "img_a"}, test_run=True))
    assert result["meta"]["kind"] == "observation"
