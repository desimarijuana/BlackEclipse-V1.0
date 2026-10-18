"""Evidence-bound data resolution for storyboards (Phase 5).

An authored spec may DECLARE bindings — `data` on a candlestick scene,
`source` on metric/comparison values — instead of hand-written numbers. This
module resolves those bindings through the injected market provider at RENDER
TIME and returns:

1. a **resolved spec** the worker renders: concrete candles and formatted
   display strings, plus a per-scene `evidence` block (source line + stale
   flag) that the renderer draws; and
2. an **EvidenceManifest** recording, for every figure, the provider, source,
   retrieval time, data timestamp, units and freshness.

Missing data FAILS the resolution (`DATA_UNAVAILABLE` with the binding path) —
there is no fabricated fallback. Stale data (the gateway's own `data_status`
verdict) resolves but is explicitly flagged in the video, the manifest, the
job output and the artifact metadata.

Formatting lives here (units/decimals belong to the video layer); the provider
returns raw normalized numbers and provenance only.
"""

from __future__ import annotations

import copy
from typing import Any

from .models import VideoError

BINDING_FIELDS: tuple[str, ...] = ("price", "changePct", "volume")
BINDING_INTERVALS: tuple[str, ...] = ("1h", "4h", "1d")

_CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥", "INR": "₹"}


# ── quoting helpers ───────────────────────────────────────────────────────────


def has_bindings(spec: Any) -> bool:
    """True when the storyboard declares at least one data binding."""
    if not isinstance(spec, dict):
        return False
    for scene in spec.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        if isinstance(scene.get("data"), dict):
            return True
        for item in list(scene.get("metrics") or []) + [scene.get("left"), scene.get("right")]:
            if isinstance(item, dict) and isinstance(item.get("source"), dict):
                return True
    return False


def format_price(value: float, currency: str | None) -> str:
    symbol = _CURRENCY_SYMBOLS.get((currency or "USD").upper(), f"{currency} " if currency else "$")
    if abs(value) >= 1000.0:
        return f"{symbol}{value:,.0f}"
    if abs(value) >= 1.0:
        return f"{symbol}{value:,.2f}"
    return f"{symbol}{value:,.4f}"


def format_percent(value: float) -> str:
    return f"{value:+.2f}%"


def format_volume(value: float) -> str:
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"{value / 1e12:.2f}T"
    if magnitude >= 1e9:
        return f"{value / 1e9:.2f}B"
    if magnitude >= 1e6:
        return f"{value / 1e6:.2f}M"
    if magnitude >= 1e3:
        return f"{value / 1e3:.1f}K"
    return f"{value:,.0f}"


def display_for_field(field: str, value: float, currency: str | None) -> str:
    if field == "changePct":
        return format_percent(value)
    if field == "volume":
        return format_volume(value)
    return format_price(value, currency)


def _short_time(iso: Any) -> str:
    text = str(iso or "")
    if "T" in text:
        date, _, rest = text.partition("T")
        return f"{date} {rest[:5]} UTC"
    return text


def _source_line(meta: dict[str, Any]) -> str:
    provider = str(meta.get("provider") or meta.get("source") or "market data")
    freshness = str(meta.get("freshness") or "unknown")
    retrieved = _short_time(meta.get("retrievedAt"))
    return f"{provider} · {freshness} · retrieved {retrieved}"


def _binding_meta(kind: str, symbol: str, meta: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "symbol": symbol,
        "provider": meta.get("provider"),
        "source": meta.get("source") or meta.get("provider"),
        "retrievedAt": meta.get("retrievedAt"),
        "dataTimestamp": meta.get("dataTimestamp"),
        "freshness": meta.get("freshness"),
        "stale": bool(meta.get("stale")),
        "quality": meta.get("quality"),
        "units": meta.get("currency"),
        "warnings": list(meta.get("warnings") or []),
        **extra,
    }


def _merge_scene_evidence(entries: list[dict[str, Any]]) -> dict[str, Any]:
    labels = []
    for entry in entries:
        label = _source_line(entry)
        if label not in labels:
            labels.append(label)
    return {
        "sources": labels,
        "sourceLine": " | ".join(labels),
        "stale": any(bool(entry.get("stale")) for entry in entries),
    }


# ── resolution ────────────────────────────────────────────────────────────────


async def resolve_storyboard(spec: dict[str, Any], provider: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Resolve every declared binding; return (resolved_spec, evidence_manifest).

    Raises `VideoError("DATA_UNAVAILABLE", ...)` naming the binding when a
    figure cannot be produced. The provider contract:

        await provider.quote(symbol, market) -> {"price","changePct","volume",
            "currency","meta": {...}}
        await provider.candles(symbol, market, interval, count) -> {"bars":
            [{"t","o","h","l","c"}], "meta": {...}}
    """
    resolved = copy.deepcopy(spec)
    bindings: list[dict[str, Any]] = []
    quote_cache: dict[tuple[str, str], dict[str, Any]] = {}

    async def quote_for(symbol: str, market: str | None) -> dict[str, Any]:
        key = (symbol, market or "")
        if key not in quote_cache:
            try:
                quote_cache[key] = await provider.quote(symbol, market)
            except VideoError:
                raise
            except Exception as exc:  # noqa: BLE001 - a provider failure is data
                raise VideoError("DATA_UNAVAILABLE", f"market data fetch failed for {symbol}: {exc}") from exc
        return quote_cache[key]

    def require_number(quote: dict[str, Any], field: str, symbol: str) -> float:
        value = quote.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise VideoError(
                "DATA_UNAVAILABLE",
                f"{symbol}: the provider returned no {field} (nothing is invented for a bound figure)",
            )
        return float(value)

    scenes = resolved.get("scenes") or []
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        kind = str(scene.get("type") or "")
        scene_bindings: list[dict[str, Any]] = []

        if kind == "candlestick" and isinstance(scene.get("data"), dict):
            data = scene.pop("data")
            symbol = str(data.get("symbol") or "")
            market = data.get("market")
            interval = str(data.get("interval") or "1d")
            count = int(data.get("count") or 30)
            try:
                fetched = await provider.candles(symbol, market, interval, count)
            except VideoError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise VideoError(
                    "DATA_UNAVAILABLE",
                    f"scenes[{index}] ({symbol}): market data fetch failed: {exc}",
                ) from exc
            bars = [bar for bar in (fetched.get("bars") or []) if isinstance(bar, dict)]
            candles: list[dict[str, float]] = []
            for bar in bars[-count:]:
                values = [bar.get("o"), bar.get("h"), bar.get("l"), bar.get("c")]
                if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in values):
                    continue
                o, h, l, c = (round(float(value), 6) for value in values)
                candles.append({"o": o, "h": max(h, o, c), "l": min(l, o, c), "c": c})
            if len(candles) < 2:
                raise VideoError(
                    "DATA_UNAVAILABLE",
                    f"scenes[{index}] ({symbol}): only {len(candles)} usable {interval} bar(s) returned",
                )
            scene["candles"] = candles
            meta = dict(fetched.get("meta") or {})
            entry = _binding_meta("candles", symbol, meta, interval=interval, rows=len(candles))
            entry["sceneIndex"] = index
            scene_bindings.append(entry)
            bindings.append(entry)

        elif kind == "metric" and isinstance(scene.get("metrics"), list):
            for item_index, item in enumerate(scene.get("metrics") or []):
                if not isinstance(item, dict) or not isinstance(item.get("source"), dict):
                    continue
                source = item.pop("source")
                symbol = str(source.get("symbol") or "")
                market = source.get("market")
                field = str(source.get("field") or "price")
                quote = await quote_for(symbol, market)
                value = require_number(quote, field, symbol)
                currency = quote.get("currency")
                item["value"] = display_for_field(field, value, currency)
                if field == "price":
                    change = quote.get("changePct")
                    if isinstance(change, (int, float)) and not isinstance(change, bool):
                        item["delta"] = format_percent(float(change))
                    entry = _binding_meta(
                        "value", symbol, quote.get("meta") or {}, field=field,
                        display=item["value"], rawValue=value,
                    )
                else:
                    entry = _binding_meta(
                        "value", symbol, quote.get("meta") or {}, field=field,
                        display=item["value"], rawValue=value,
                    )
                entry["sceneIndex"] = index
                entry["itemIndex"] = item_index
                scene_bindings.append(entry)
                bindings.append(entry)

        elif kind == "comparison":
            for side in ("left", "right"):
                pane = scene.get(side)
                if not isinstance(pane, dict) or not isinstance(pane.get("source"), dict):
                    continue
                source = pane.pop("source")
                symbol = str(source.get("symbol") or "")
                market = source.get("market")
                field = str(source.get("field") or "price")
                quote = await quote_for(symbol, market)
                value = require_number(quote, field, symbol)
                pane["value"] = display_for_field(field, value, quote.get("currency"))
                entry = _binding_meta(
                    "value", symbol, quote.get("meta") or {}, field=field,
                    display=pane["value"], rawValue=value,
                )
                entry["sceneIndex"] = index
                entry["pane"] = side
                scene_bindings.append(entry)
                bindings.append(entry)

        if scene_bindings:
            scene["evidence"] = _merge_scene_evidence(scene_bindings)

    manifest = {
        "bindings": bindings,
        "providers": sorted({str(entry.get("provider")) for entry in bindings if entry.get("provider")}),
        "stale": any(bool(entry.get("stale")) for entry in bindings),
        "warnings": sorted(
            {warning for entry in bindings for warning in (entry.get("warnings") or [])}
        ),
    }
    return resolved, manifest


__all__ = [
    "BINDING_FIELDS",
    "BINDING_INTERVALS",
    "display_for_field",
    "format_percent",
    "format_price",
    "format_volume",
    "has_bindings",
    "resolve_storyboard",
]
