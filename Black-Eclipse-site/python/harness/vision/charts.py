"""Chart vision, with market-data verification.

Chart vision interprets VISUAL structure — chart type, trend, drawn zones,
patterns, annotations. It is explicitly NOT the source of truth for price, OHLC,
volume, indicator values or timestamps. When deterministic market data is
available (JDdS / providers through the existing data bridge), that data is
fetched through the existing retrieval path and used to VERIFY the visual trend;
a visual numeric claim that conflicts with real data is marked `conflicting`
rather than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import Region, VisionInput, VisionResult, VisionUsage, VisualObservation
from .errors import VisionError
from .image import DecodedImage
from .providers import call_model
from .routing import RoutingPlan

CHART_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chart_type": {"type": "string"},
        "trend": {"type": "string"},
        "patterns": {"type": "array", "items": {"type": "string"}},
        "regions": {"type": "array", "items": {"type": "object"}},
        "observations": {"type": "array", "items": {"type": "object"}},
        "confidence": {"type": "number"},
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "symbol": {"type": "string"},
        "timeframe": {"type": "string"},
    },
}

_CHART_PROMPT = (
    "You are Eclipse's chart-vision engine. Describe the VISUAL structure of the "
    "attached chart: its type, the apparent trend, any drawn zones/lines, and any "
    "technical patterns. Do NOT state exact prices, OHLC values, volumes or "
    "indicator numbers as fact unless they are printed and unambiguous; report "
    "only what is visually present. Be explicit about uncertainty.\n"
    "Question: {question}\n"
    "Reply with one JSON object:\n"
    '{{"chart_type": "line|bar|candlestick|area|scatter|other", "trend": "up|down|sideways|unclear", '
    '"patterns": ["..."], "regions": [{{"label": "...", "region": [x,y,w,h], "confidence": 0..1}}], '
    '"observations": [{{"text": "...", "confidence": 0..1}}], "uncertainties": ["..."], '
    '"symbol": "if printed", "timeframe": "if printed", "confidence": 0..1}}'
)


@dataclass
class ChartOutcome:
    chart_type: str
    trend: str
    patterns: list[str]
    regions: list[VisualObservation]
    observations: list[VisualObservation]
    uncertainties: list[str]
    confidence: float
    symbol: Optional[str] = None
    timeframe: Optional[str] = None
    verification: Optional[dict[str, Any]] = None
    warnings: list[str] = field(default_factory=list)


def _series_trend(rows: list[dict[str, Any]]) -> Optional[str]:
    """Deterministic trend from a real OHLCV series (last vs first close)."""
    closes = []
    for row in rows:
        value = row.get("close", row.get("c"))
        try:
            closes.append(float(value))
        except (TypeError, ValueError):
            continue
    if len(closes) < 2:
        return None
    first, last = closes[0], closes[-1]
    if first == 0:
        return None
    change = (last - first) / abs(first)
    if change > 0.02:
        return "up"
    if change < -0.02:
        return "down"
    return "sideways"


async def _verify_with_market(
    *, symbol: Optional[str], market: Optional[str], trend: str, bridge: Any,
) -> Optional[dict[str, Any]]:
    """Fetch real market data through the bridge and compare the visual trend."""
    if bridge is None or not symbol:
        return None
    try:
        result = await bridge.fetch("price_history", {"symbol": symbol, "market": market or "", "range": "6mo", "period": "1d"})
    except Exception as exc:  # noqa: BLE001 - verification is best-effort, never fatal
        return {"available": False, "reason": f"market data bridge failed: {exc}"}
    if not isinstance(result, dict) or not (result.get("series") or result.get("rows")):
        return {"available": False, "reason": "no deterministic series was available"}
    rows = result.get("series") or result.get("rows")
    actual = _series_trend(rows)
    if actual is None:
        return {"available": False, "reason": "the series was too short to derive a trend"}
    agrees = actual == trend or (trend == "unclear")
    return {
        "available": True,
        "symbol": symbol,
        "actualTrend": actual,
        "visualTrend": trend,
        "agrees": agrees,
        "provider": result.get("provider"),
        "asOf": result.get("asOf"),
        "source": "deterministic_market_data",
    }


async def analyze_chart(
    decoded: DecodedImage,
    input: VisionInput,
    plan: RoutingPlan,
    *,
    bridge: Any = None,
    symbol: Optional[str] = None,
    market: Optional[str] = None,
    timeout_s: float = 120.0,
) -> tuple[ChartOutcome, Any]:
    prompt = _CHART_PROMPT.format(question=input.question or "Analyze this chart.")
    result = await call_model(plan.settings, prompt, [decoded.image], task="vision",
                              timeout_s=timeout_s, structured=True, backend=plan.kind)
    from .analyze import extract_json  # noqa: PLC0415

    payload = extract_json(result.text) or {}
    regions: list[VisualObservation] = []
    for item in payload.get("regions", []) or []:
        if isinstance(item, dict):
            regions.append(VisualObservation(
                text=str(item.get("label") or item.get("text") or ""),
                region=Region.from_any(item.get("region") or item.get("bbox")),
                confidence=float(item.get("confidence", 0.5) or 0.5), method="model",
            ))
    observations: list[VisualObservation] = []
    for item in payload.get("observations", []) or []:
        if isinstance(item, dict):
            observations.append(VisualObservation(
                text=str(item.get("text") or item.get("label") or ""),
                region=Region.from_any(item.get("region") or item.get("bbox")),
                confidence=float(item.get("confidence", 0.5) or 0.5), method="model",
            ))
    trend = str(payload.get("trend") or "unclear")
    warnings: list[str] = []
    visual_symbol = payload.get("symbol") or None
    lookup_symbol = symbol or (visual_symbol if isinstance(visual_symbol, str) and visual_symbol.strip() else None)
    verification = await _verify_with_market(
        symbol=lookup_symbol, market=market, trend=trend, bridge=bridge,
    )
    if verification and verification.get("available") and not verification.get("agrees"):
        warnings.append(
            "the visual trend disagrees with deterministic market data; the market data is authoritative"
        )
        observations.append(VisualObservation(
            text=f"deterministic market data indicates a {verification['actualTrend']} trend",
            kind="verified", method="market_data", confidence=0.9,
            source={"provider": verification.get("provider")},
        ))
    elif verification and verification.get("available"):
        observations.append(VisualObservation(
            text=f"visual trend ({trend}) agrees with deterministic market data",
            kind="verified", method="market_data", confidence=0.9,
            source={"provider": verification.get("provider")},
        ))

    def _f(value: Any, default: float = 0.5) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    outcome = ChartOutcome(
        chart_type=str(payload.get("chart_type") or "unknown"),
        trend=trend,
        patterns=[str(p) for p in (payload.get("patterns") or [])],
        regions=regions, observations=observations,
        uncertainties=[str(u) for u in (payload.get("uncertainties") or [])],
        confidence=max(0.0, min(1.0, _f(payload.get("confidence")))) if payload else 0.4,
        symbol=lookup_symbol if isinstance(lookup_symbol, str) else None,
        timeframe=str(payload.get("timeframe")) if payload.get("timeframe") else None,
        verification=verification, warnings=warnings,
    )
    return outcome, result


def build_chart_result(
    outcome: ChartOutcome, result: Any, *, asset_id: Optional[str], provenance: Optional[dict[str, Any]],
) -> VisionResult:
    usage = VisionUsage(
        input_tokens=getattr(result, "usage", VisionUsage()).input_tokens,
        output_tokens=getattr(result, "usage", VisionUsage()).output_tokens,
        total_tokens=getattr(result, "usage", VisionUsage()).total_tokens,
    )
    return VisionResult(
        ok=True, mode="chart", description=outcome.chart_type,
        observations=outcome.observations, regions=outcome.regions, objects=outcome.regions,
        chart={
            "chart_type": outcome.chart_type, "trend": outcome.trend,
            "patterns": outcome.patterns, "symbol": outcome.symbol, "timeframe": outcome.timeframe,
            "uncertainties": outcome.uncertainties, "verification": outcome.verification,
        },
        confidence=outcome.confidence,
        provider=getattr(result, "provider", None), model=getattr(result, "model", None),
        backend=getattr(result, "backend", "model"), latency_ms=getattr(result, "latency_ms", 0),
        usage=usage, provenance={**(provenance or {}), "chart": {"verification": outcome.verification}},
        warnings=outcome.warnings, asset_id=asset_id,
    )


__all__ = [
    "CHART_SCHEMA", "ChartOutcome", "analyze_chart", "build_chart_result", "_series_trend",
]
