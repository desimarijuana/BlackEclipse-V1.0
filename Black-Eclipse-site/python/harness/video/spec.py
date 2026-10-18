"""The canonical storyboard schema (schemaVersion 2 and 3) and its validator.

This is the ONE authority for what a video project may contain; the Rust worker
re-checks the load-bearing bounds defensively, but every user-visible problem is
reported HERE, with a precise path (`scenes[2].metrics[0].label: ...`), before a
job is ever queued.

Schema (all keys camelCase):

    {
      "schemaVersion": 2 | 3,
      "format": "landscape",                     # closed set (1920x1080@30)
      "style": {"theme": "dark", "accent": "#3b82f6"},   # optional
      "scenes": [ {scene}, ... ]                 # 1-12, ordered
    }

Scene common keys: `type` (intro|metric|candlestick|comparison|timeline|quote|
outro), `durationSeconds` (1-30), `transition` (`cut` default | `fade`).

**schemaVersion 3 adds data bindings (Phase 5).** A scene may DECLARE where a
figure comes from instead of hand-writing it; the render job resolves bindings
through the Market Data Gateway and fills concrete values plus an `evidence`
block (missing data fails the render; stale data is flagged):

- candlestick: `"data": {"symbol", "market"?, "interval": "1h"|"4h"|"1d", "count": 2-60}`
  — exactly one of `candles` (static) or `data` (bound).
- metric item: `"source": {"symbol", "market"?, "field": "price"|"changePct"|"volume"}`
  — when bound, `value`/`delta` must be OMITTED (no mixing authored and fetched
  numbers).
- comparison pane: same `source` rule (bound pane omits `value`).

Version 2 specs (static display strings only) remain fully valid. Unknown keys
are rejected (never silently dropped); the complete total must fit 300 s.
"""

from __future__ import annotations

from typing import Any, Optional

from .data import BINDING_FIELDS, BINDING_INTERVALS

SCHEMA_VERSION = 3
SUPPORTED_VERSIONS: tuple[int, ...] = (2, 3)
FORMATS: tuple[str, ...] = ("landscape",)
THEMES: tuple[str, ...] = ("dark",)
TRANSITIONS: tuple[str, ...] = ("cut", "fade")
SCENE_TYPES: tuple[str, ...] = (
    "intro", "metric", "candlestick", "comparison", "timeline", "quote", "outro",
)

MIN_SCENES = 1
MAX_SCENES = 12
MIN_SCENE_SECONDS = 1.0
MAX_SCENE_SECONDS = 30.0
MAX_TOTAL_SECONDS = 300.0

_COMMON_KEYS = {"type", "durationSeconds", "transition"}
_TYPE_KEYS: dict[str, set[str]] = {
    "intro": {"title", "subtitle"},
    "outro": {"title", "subtitle"},
    "metric": {"title", "metrics"},
    "candlestick": {"title", "symbol", "candles"},
    "comparison": {"title", "left", "right", "winner"},
    "timeline": {"title", "events"},
    "quote": {"text", "attribution"},
}
# schemaVersion 3 binding keys, per scene type.
_V3_SCENE_KEYS: dict[str, set[str]] = {
    "candlestick": {"data"},
    "metric": set(),
    "comparison": set(),
}
_V3_ITEM_KEYS: dict[str, set[str]] = {
    "metric": {"source"},
    "comparison": {"source"},
}


# ── primitives ────────────────────────────────────────────────────────────────


def _problems_for_unknown_keys(obj: Any, allowed: set[str], path: str, problems: list[str]) -> None:
    if not isinstance(obj, dict):
        return
    for key in obj:
        if key not in allowed:
            problems.append(f"{path}.{key}: unknown field (allowed: {', '.join(sorted(allowed))})")


def _check_text(
    problems: list[str], value: Any, path: str, *, required: bool,
    max_length: int, min_length: int = 1,
) -> None:
    if value is None:
        if required:
            problems.append(f"{path}: is required")
        return
    if not isinstance(value, str):
        problems.append(f"{path}: must be a string")
        return
    text = value.strip()
    if not text:
        if required:
            problems.append(f"{path}: must not be empty")
        return
    if len(text) < min_length or len(text) > max_length:
        problems.append(f"{path}: must be {min_length}-{max_length} characters")


def _check_hex(problems: list[str], value: Any, path: str) -> None:
    if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
        problems.append(f"{path}: must be a #RRGGBB color")
        return
    try:
        int(value[1:], 16)
    except ValueError:
        problems.append(f"{path}: must be a #RRGGBB color")


def _check_source(problems: list[str], source: Any, path: str) -> None:
    if not isinstance(source, dict):
        problems.append(f"{path}: must be an object")
        return
    _problems_for_unknown_keys(source, {"symbol", "market", "field"}, path, problems)
    _check_text(problems, source.get("symbol"), f"{path}.symbol", required=True, max_length=32)
    _check_text(problems, source.get("market"), f"{path}.market", required=False, max_length=16)
    field = source.get("field")
    if field not in BINDING_FIELDS:
        problems.append(f"{path}.field: must be one of {', '.join(BINDING_FIELDS)}")


def _check_candle_data(problems: list[str], data: Any, path: str) -> None:
    if not isinstance(data, dict):
        problems.append(f"{path}: must be an object")
        return
    _problems_for_unknown_keys(data, {"symbol", "market", "interval", "count"}, path, problems)
    _check_text(problems, data.get("symbol"), f"{path}.symbol", required=True, max_length=32)
    _check_text(problems, data.get("market"), f"{path}.market", required=False, max_length=16)
    interval = data.get("interval")
    if interval not in BINDING_INTERVALS:
        problems.append(f"{path}.interval: must be one of {', '.join(BINDING_INTERVALS)}")
    count = data.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or not (2 <= count <= 60):
        problems.append(f"{path}.count: must be an integer 2-60")


# ── scene validators ──────────────────────────────────────────────────────────


def _validate_scene(scene: Any, index: int, problems: list[str], version: int) -> Optional[float]:
    at = f"scenes[{index}]"
    if not isinstance(scene, dict):
        problems.append(f"{at}: must be an object")
        return None
    kind = scene.get("type")
    if kind not in SCENE_TYPES:
        problems.append(f"{at}.type: must be one of {', '.join(SCENE_TYPES)}")
        return None
    allowed = _COMMON_KEYS | _TYPE_KEYS[kind]
    if version >= 3:
        allowed = allowed | _V3_SCENE_KEYS.get(kind, set())
    _problems_for_unknown_keys(scene, allowed, at, problems)

    duration = scene.get("durationSeconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        problems.append(f"{at}.durationSeconds: is required and must be a number")
        duration = None
    elif not (MIN_SCENE_SECONDS - 1e-9 <= float(duration) <= MAX_SCENE_SECONDS + 1e-9):
        problems.append(
            f"{at}.durationSeconds: must be {MIN_SCENE_SECONDS:.0f}-{MAX_SCENE_SECONDS:.0f} seconds"
        )

    transition = scene.get("transition")
    if transition is not None and transition not in TRANSITIONS:
        problems.append(f"{at}.transition: must be `cut` or `fade`")

    if kind in ("intro", "outro"):
        _check_text(problems, scene.get("title"), f"{at}.title", required=True, max_length=80)
        _check_text(problems, scene.get("subtitle"), f"{at}.subtitle", required=False, max_length=120)
    elif kind == "metric":
        _check_text(problems, scene.get("title"), f"{at}.title", required=True, max_length=80)
        metrics = scene.get("metrics")
        if not isinstance(metrics, list) or not (1 <= len(metrics) <= 4):
            problems.append(f"{at}.metrics: must be a list of 1-4 entries")
        else:
            for metric_index, metric in enumerate(metrics):
                metric_at = f"{at}.metrics[{metric_index}]"
                if not isinstance(metric, dict):
                    problems.append(f"{metric_at}: must be an object")
                    continue
                item_keys = {"label", "value", "delta"}
                if version >= 3:
                    item_keys = item_keys | _V3_ITEM_KEYS["metric"]
                _problems_for_unknown_keys(metric, item_keys, metric_at, problems)
                _check_text(problems, metric.get("label"), f"{metric_at}.label", required=True, max_length=40)
                if metric.get("source") is not None:
                    _check_source(problems, metric.get("source"), f"{metric_at}.source")
                    if metric.get("value") is not None or metric.get("delta") is not None:
                        problems.append(
                            f"{metric_at}: `value`/`delta` must be omitted when `source` is bound"
                        )
                else:
                    _check_text(problems, metric.get("value"), f"{metric_at}.value", required=True, max_length=20)
                    _check_text(problems, metric.get("delta"), f"{metric_at}.delta", required=False, max_length=12)
    elif kind == "candlestick":
        _check_text(problems, scene.get("title"), f"{at}.title", required=True, max_length=80)
        _check_text(problems, scene.get("symbol"), f"{at}.symbol", required=True, max_length=12)
        data = scene.get("data") if version >= 3 else None
        if data is not None:
            _check_candle_data(problems, data, f"{at}.data")
            if scene.get("candles") is not None:
                problems.append(f"{at}: `candles` must be omitted when `data` is bound")
        else:
            candles = scene.get("candles")
            if not isinstance(candles, list) or not (2 <= len(candles) <= 60):
                problems.append(f"{at}.candles: must be a list of 2-60 candles (or use `data`)")
            else:
                for candle_index, candle in enumerate(candles):
                    candle_at = f"{at}.candles[{candle_index}]"
                    if not isinstance(candle, dict):
                        problems.append(f"{candle_at}: must be an object")
                        continue
                    _problems_for_unknown_keys(candle, {"o", "h", "l", "c"}, candle_at, problems)
                    values: dict[str, float] = {}
                    ok = True
                    for key in ("o", "h", "l", "c"):
                        value = candle.get(key)
                        if not isinstance(value, (int, float)) or isinstance(value, bool):
                            problems.append(f"{candle_at}.{key}: is required and must be a number")
                            ok = False
                        else:
                            values[key] = float(value)
                    if ok and (values["h"] < max(values["o"], values["c"]) or values["l"] > min(values["o"], values["c"])):
                        problems.append(
                            f"{candle_at}: inconsistent candle (h >= max(o,c) and l <= min(o,c) required)"
                        )
    elif kind == "comparison":
        _check_text(problems, scene.get("title"), f"{at}.title", required=True, max_length=80)
        for side in ("left", "right"):
            pane = scene.get(side)
            if pane is None:
                problems.append(f"{at}.{side}: is required")
                continue
            pane_at = f"{at}.{side}"
            if not isinstance(pane, dict):
                problems.append(f"{pane_at}: must be an object")
                continue
            item_keys = {"label", "value", "detail"}
            if version >= 3:
                item_keys = item_keys | _V3_ITEM_KEYS["comparison"]
            _problems_for_unknown_keys(pane, item_keys, pane_at, problems)
            _check_text(problems, pane.get("label"), f"{pane_at}.label", required=True, max_length=40)
            if pane.get("source") is not None:
                _check_source(problems, pane.get("source"), f"{pane_at}.source")
                if pane.get("value") is not None:
                    problems.append(f"{pane_at}: `value` must be omitted when `source` is bound")
            else:
                _check_text(problems, pane.get("value"), f"{pane_at}.value", required=True, max_length=20)
            _check_text(problems, pane.get("detail"), f"{pane_at}.detail", required=False, max_length=60)
        winner = scene.get("winner")
        if winner is not None and winner not in ("left", "right"):
            problems.append(f"{at}.winner: must be `left` or `right`")
    elif kind == "timeline":
        _check_text(problems, scene.get("title"), f"{at}.title", required=True, max_length=80)
        events = scene.get("events")
        if not isinstance(events, list) or not (2 <= len(events) <= 6):
            problems.append(f"{at}.events: must be a list of 2-6 events")
        else:
            for event_index, event in enumerate(events):
                event_at = f"{at}.events[{event_index}]"
                if not isinstance(event, dict):
                    problems.append(f"{event_at}: must be an object")
                    continue
                _problems_for_unknown_keys(event, {"label", "detail"}, event_at, problems)
                _check_text(problems, event.get("label"), f"{event_at}.label", required=True, max_length=48)
                _check_text(problems, event.get("detail"), f"{event_at}.detail", required=False, max_length=80)
    elif kind == "quote":
        _check_text(problems, scene.get("text"), f"{at}.text", required=True, max_length=280)
        _check_text(problems, scene.get("attribution"), f"{at}.attribution", required=False, max_length=80)

    return float(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None


# ── the schema ────────────────────────────────────────────────────────────────


def validate_storyboard(spec: Any) -> list[str]:
    """Every problem in the spec, as precise human/agent-readable strings."""
    if not isinstance(spec, dict):
        return ["spec: must be an object"]
    problems: list[str] = []
    _problems_for_unknown_keys(
        spec, {"schemaVersion", "format", "style", "scenes"}, "spec", problems
    )
    version = spec.get("schemaVersion")
    if version not in SUPPORTED_VERSIONS:
        problems.append(
            f"spec.schemaVersion: must be one of {', '.join(str(v) for v in SUPPORTED_VERSIONS)}"
        )
        return problems
    if spec.get("format") not in FORMATS:
        problems.append(f"spec.format: must be one of {', '.join(FORMATS)} (1920x1080@30)")
    style = spec.get("style")
    if style is not None:
        if not isinstance(style, dict):
            problems.append("spec.style: must be an object")
        else:
            _problems_for_unknown_keys(style, {"theme", "accent"}, "spec.style", problems)
            theme = style.get("theme")
            if theme is not None and theme not in THEMES:
                problems.append(f"spec.style.theme: must be one of {', '.join(THEMES)}")
            if style.get("accent") is not None:
                _check_hex(problems, style.get("accent"), "spec.style.accent")

    scenes = spec.get("scenes")
    if not isinstance(scenes, list) or not (MIN_SCENES <= len(scenes) <= MAX_SCENES):
        problems.append(f"spec.scenes: must be a list of {MIN_SCENES}-{MAX_SCENES} scenes")
        return problems

    total = 0.0
    for index, scene in enumerate(scenes):
        duration = _validate_scene(scene, index, problems, int(version))
        if duration is not None:
            total += duration
    if total > MAX_TOTAL_SECONDS:
        problems.append(f"spec.scenes: the storyboard totals {total:.1f}s; the cap is {MAX_TOTAL_SECONDS:.0f}s")
    return problems


def total_seconds(spec: dict[str, Any]) -> float:
    """The resolved duration (sum of scene durations) — for summaries."""
    scenes = spec.get("scenes") if isinstance(spec, dict) else None
    if not isinstance(scenes, list):
        return 0.0
    total = 0.0
    for scene in scenes:
        if isinstance(scene, dict):
            value = scene.get("durationSeconds")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
    return total


__all__ = [
    "BINDING_FIELDS",
    "BINDING_INTERVALS",
    "SCHEMA_VERSION",
    "SCENE_TYPES",
    "SUPPORTED_VERSIONS",
    "total_seconds",
    "validate_storyboard",
]
