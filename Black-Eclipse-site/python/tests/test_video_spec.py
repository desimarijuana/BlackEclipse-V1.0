"""The storyboard schema validator: every problem class gets a precise path."""

from __future__ import annotations

from harness.video.spec import total_seconds, validate_storyboard


def _valid_spec() -> dict:
    return {
        "schemaVersion": 2,
        "format": "landscape",
        "style": {"theme": "dark", "accent": "#3b82f6"},
        "scenes": [
            {"type": "intro", "durationSeconds": 3, "title": "Welcome", "subtitle": "A recap"},
            {
                "type": "metric", "durationSeconds": 4, "transition": "fade", "title": "Metrics",
                "metrics": [
                    {"label": "Price", "value": "68,240", "delta": "+2.4%"},
                    {"label": "Volume", "value": "38.2B"},
                ],
            },
            {
                "type": "candlestick", "durationSeconds": 6, "title": "Candles", "symbol": "BTC",
                "candles": [
                    {"o": 10, "h": 12, "l": 9, "c": 11},
                    {"o": 11, "h": 13, "l": 10, "c": 10.5},
                ],
            },
            {
                "type": "comparison", "durationSeconds": 4, "title": "Versus",
                "left": {"label": "Support", "value": "$66k", "detail": "Held twice"},
                "right": {"label": "Resistance", "value": "$71k"},
                "winner": "right",
            },
            {
                "type": "timeline", "durationSeconds": 4, "title": "The week",
                "events": [{"label": "Mon", "detail": "Inflows"}, {"label": "Fri", "detail": "Expiry"}],
            },
            {"type": "quote", "durationSeconds": 3, "text": "Stay rational.", "attribution": "Someone"},
            {"type": "outro", "durationSeconds": 2, "title": "Bye"},
        ],
    }


def test_valid_storyboard_passes():
    assert validate_storyboard(_valid_spec()) == []
    assert total_seconds(_valid_spec()) == 26.0


def test_unknown_keys_are_rejected_everywhere():
    spec = _valid_spec()
    spec["extraTop"] = True
    spec["scenes"][0]["extraScene"] = 1
    spec["scenes"][1]["metrics"][0]["extraMetric"] = "x"
    problems = validate_storyboard(spec)
    assert any("spec.extraTop" in p for p in problems)
    assert any("scenes[0].extraScene" in p for p in problems)
    assert any("scenes[1].metrics[0].extraMetric" in p for p in problems)


def test_header_and_bounds():
    problems = validate_storyboard({"schemaVersion": 1, "format": "portrait", "scenes": []})
    assert any("schemaVersion" in p for p in problems)
    spec = _valid_spec()
    spec["schemaVersion"] = 3
    spec["format"] = "portrait"
    spec["scenes"] = []
    problems = validate_storyboard(spec)
    assert any("format" in p for p in problems)
    assert any("1-12 scenes" in p for p in problems)
    spec = _valid_spec()
    spec["style"]["accent"] = "blue"
    spec["style"]["theme"] = "light"
    assert any("accent" in p for p in validate_storyboard(spec))
    assert any("theme" in p for p in validate_storyboard(spec))


def test_duration_bounds_and_total_cap():
    spec = _valid_spec()
    spec["scenes"][0]["durationSeconds"] = 0.5
    assert any("durationSeconds" in p for p in validate_storyboard(spec))
    spec = _valid_spec()
    spec["scenes"][0]["durationSeconds"] = 31
    assert any("durationSeconds" in p for p in validate_storyboard(spec))
    spec = _valid_spec()
    spec["scenes"] = [{"type": "outro", "durationSeconds": 30, "title": "x"} for _ in range(11)]
    assert any("cap" in p for p in validate_storyboard(spec))


def test_scene_specific_requirements():
    spec = _valid_spec()
    spec["scenes"][0].pop("title")
    spec["scenes"][1]["metrics"] = [{"label": "only 5 values"}] * 5
    spec["scenes"][2]["candles"] = [{"o": 1, "h": 2, "l": 0.5, "c": 1.5}]
    spec["scenes"][3].pop("right")
    spec["scenes"][4]["events"] = [{"label": "one"}]
    spec["scenes"][5]["text"] = "   "
    problems = validate_storyboard(spec)
    assert any("scenes[0].title: is required" in p for p in problems)
    assert any("scenes[1].metrics: must be a list of 1-4" in p for p in problems)
    assert any("scenes[2].candles: must be a list of 2-60" in p for p in problems)
    assert any("scenes[3].right: is required" in p for p in problems)
    assert any("scenes[4].events: must be a list of 2-6" in p for p in problems)
    assert any("scenes[5].text" in p for p in problems)


def test_inconsistent_candle_and_bad_transition_and_winner():
    spec = _valid_spec()
    spec["scenes"][2]["candles"] = [
        {"o": 10, "h": 9, "l": 8, "c": 11},
        {"o": 11, "h": 13, "l": 10, "c": 12},
    ]
    spec["scenes"][1]["transition"] = "wipe"
    spec["scenes"][3]["winner"] = "me"
    problems = validate_storyboard(spec)
    assert any("inconsistent candle" in p for p in problems)
    assert any("transition" in p for p in problems)
    assert any("winner" in p for p in problems)


def test_non_object_spec():
    assert validate_storyboard([]) == ["spec: must be an object"]


# ── schemaVersion 3: data bindings (Phase 5) ─────────────────────────────────


def _v3_spec() -> dict:
    return {
        "schemaVersion": 3,
        "format": "landscape",
        "scenes": [
            {"type": "intro", "durationSeconds": 2, "title": "Bound"},
            {
                "type": "metric", "durationSeconds": 4, "title": "Metrics",
                "metrics": [
                    {"label": "Price", "source": {"symbol": "BTC-USD", "field": "price"}},
                    {"label": "Note", "value": "static ok"},
                ],
            },
            {
                "type": "candlestick", "durationSeconds": 5, "title": "Candles", "symbol": "BTC-USD",
                "data": {"symbol": "BTC-USD", "interval": "1d", "count": 14},
            },
            {
                "type": "comparison", "durationSeconds": 4, "title": "VS",
                "left": {"label": "BTC", "source": {"symbol": "BTC-USD", "field": "price"}},
                "right": {"label": "ETH", "value": "$2,410"},
            },
        ],
    }


def test_v3_bindings_validate():
    assert validate_storyboard(_v3_spec()) == []


def test_v2_rejects_binding_keys_as_unknown():
    spec = _v3_spec()
    spec["schemaVersion"] = 2
    problems = validate_storyboard(spec)
    assert any("scenes[1].metrics[0].source" in p for p in problems)
    assert any("scenes[2].data" in p for p in problems)


def test_unsupported_version_rejected():
    spec = _v3_spec()
    spec["schemaVersion"] = 4
    assert any("schemaVersion" in p for p in validate_storyboard(spec))


def test_v3_mixing_rules():
    spec = _v3_spec()
    spec["scenes"][1]["metrics"][0]["value"] = "42"
    spec["scenes"][2]["candles"] = [{"o": 1, "h": 2, "l": 0.5, "c": 1.5}]
    spec["scenes"][3]["left"]["value"] = "$1"
    problems = validate_storyboard(spec)
    assert any("omitted when `source` is bound" in p for p in problems)
    assert any("`candles` must be omitted when `data` is bound" in p for p in problems)


def test_v3_binding_shapes():
    spec = _v3_spec()
    spec["scenes"][1]["metrics"][0]["source"]["field"] = "mood"
    spec["scenes"][2]["data"]["interval"] = "5m"
    spec["scenes"][2]["data"]["count"] = 1
    spec["scenes"][3]["left"]["source"].pop("symbol")
    problems = validate_storyboard(spec)
    assert any(".field:" in p for p in problems)
    assert any(".interval:" in p for p in problems)
    assert any(".count:" in p for p in problems)
    assert any("source.symbol: is required" in p for p in problems)
