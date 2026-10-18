"""Data bindings (schemaVersion 3): resolution, formatting, provenance, and the
no-invention rules — missing data fails, stale data is flagged."""

from __future__ import annotations

import asyncio

import pytest

from harness.video.data import (
    format_percent,
    format_price,
    format_volume,
    has_bindings,
    resolve_storyboard,
)
from harness.video.models import VideoError

from video_fakes import FakeMarketProvider


def _metric_spec(*, field: str = "price", schema: int = 3) -> dict:
    return {
        "schemaVersion": schema,
        "format": "landscape",
        "scenes": [{
            "type": "metric", "durationSeconds": 4, "title": "Metrics",
            "metrics": [{"label": "Price", "source": {"symbol": "BTC-USD", "field": field}}],
        }],
    }


def _candle_spec() -> dict:
    return {
        "schemaVersion": 3,
        "format": "landscape",
        "scenes": [{
            "type": "candlestick", "durationSeconds": 5, "title": "Candles",
            "symbol": "BTC-USD", "data": {"symbol": "BTC-USD", "interval": "1d", "count": 10},
        }],
    }


def test_formatters():
    assert format_price(68240.5, "USD") == "$68,240"
    assert format_price(12.3456, "EUR") == "€12.35"
    assert format_price(0.1234, "USD") == "$0.1234"
    assert format_percent(2.41) == "+2.41%"
    assert format_percent(-1.2) == "-1.20%"
    assert format_volume(3.82e10) == "38.20B"
    assert format_volume(1.25e6) == "1.25M"
    assert format_volume(9500) == "9.5K"
    assert format_volume(420) == "420"


def test_has_bindings_detects_each_shape():
    assert has_bindings(_metric_spec()) is True
    assert has_bindings(_candle_spec()) is True
    comparison = {
        "schemaVersion": 3, "format": "landscape",
        "scenes": [{
            "type": "comparison", "durationSeconds": 4, "title": "VS",
            "left": {"label": "BTC", "source": {"symbol": "BTC-USD", "field": "price"}},
            "right": {"label": "ETH", "value": "$2,410"},
        }],
    }
    assert has_bindings(comparison) is True
    static = {"schemaVersion": 2, "format": "landscape",
              "scenes": [{"type": "intro", "durationSeconds": 2, "title": "x"}]}
    assert has_bindings(static) is False


def test_metric_price_binding_resolves_display_and_delta():
    resolved, manifest = asyncio.run(resolve_storyboard(_metric_spec(), FakeMarketProvider()))
    item = resolved["scenes"][0]["metrics"][0]
    assert item["value"] == "$68,240" and item["delta"] == "+2.41%"
    assert "source" not in item
    assert resolved["scenes"][0]["evidence"]["stale"] is False
    binding = manifest["bindings"][0]
    assert binding["kind"] == "value" and binding["field"] == "price"
    assert binding["display"] == "$68,240" and binding["rawValue"] == 68240.5
    assert binding["provider"] == "yahoo" and binding["retrievedAt"]
    assert manifest["providers"] == ["yahoo"] and manifest["stale"] is False


def test_quote_cache_avoids_duplicate_fetches():
    spec = _metric_spec()
    spec["scenes"][0]["metrics"].append(
        {"label": "Volume", "source": {"symbol": "BTC-USD", "field": "volume"}}
    )
    provider = FakeMarketProvider()
    resolved, manifest = asyncio.run(resolve_storyboard(spec, provider))
    assert [call[0] for call in provider.calls] == ["quote"]
    assert [item["value"] for item in resolved["scenes"][0]["metrics"]] == ["$68,240", "38.20B"]
    assert len(manifest["bindings"]) == 2


def test_candle_binding_resolves_bars_and_enforces_parity():
    resolved, manifest = asyncio.run(resolve_storyboard(_candle_spec(), FakeMarketProvider(bars=10)))
    scene = resolved["scenes"][0]
    assert "data" not in scene
    assert len(scene["candles"]) == 10
    for candle in scene["candles"]:
        assert candle["h"] >= max(candle["o"], candle["c"])
        assert candle["l"] <= min(candle["o"], candle["c"])
    binding = manifest["bindings"][0]
    assert binding["kind"] == "candles" and binding["rows"] == 10
    assert scene["evidence"]["stale"] is False


def test_missing_field_fails_without_inventing():
    with pytest.raises(VideoError) as exc:
        asyncio.run(resolve_storyboard(_metric_spec(), FakeMarketProvider(missing_field=True)))
    assert exc.value.code == "DATA_UNAVAILABLE"
    assert "no price" in exc.value.message


def test_provider_failure_maps_to_data_unavailable():
    with pytest.raises(VideoError) as exc:
        asyncio.run(resolve_storyboard(_candle_spec(), FakeMarketProvider(fail=True)))
    assert exc.value.code == "DATA_UNAVAILABLE"
    assert "scenes[0]" in exc.value.message


def test_short_history_fails():
    with pytest.raises(VideoError) as exc:
        asyncio.run(resolve_storyboard(_candle_spec(), FakeMarketProvider(short_bars=True)))
    assert exc.value.code == "DATA_UNAVAILABLE"
    assert "usable" in exc.value.message


def test_stale_propagates_to_scene_and_manifest():
    resolved, manifest = asyncio.run(
        resolve_storyboard(_candle_spec(), FakeMarketProvider(stale=True))
    )
    assert resolved["scenes"][0]["evidence"]["stale"] is True
    assert manifest["stale"] is True
    assert manifest["bindings"][0]["stale"] is True


def test_comparison_panes_bind_values():
    spec = {
        "schemaVersion": 3, "format": "landscape",
        "scenes": [{
            "type": "comparison", "durationSeconds": 4, "title": "VS",
            "left": {"label": "BTC", "source": {"symbol": "BTC-USD", "field": "price"}},
            "right": {"label": "Momentum", "source": {"symbol": "BTC-USD", "field": "changePct"}},
        }],
    }
    resolved, manifest = asyncio.run(resolve_storyboard(spec, FakeMarketProvider()))
    left = resolved["scenes"][0]["left"]
    right = resolved["scenes"][0]["right"]
    assert left["value"] == "$68,240" and "source" not in left
    assert right["value"] == "+2.41%" and "source" not in right
    assert [entry["pane"] for entry in manifest["bindings"]] == ["left", "right"]
