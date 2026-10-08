"""Run-level vision-result collection.

Mirrors `source_collector.SourceCollector`: a DERIVED read model over the vision
results a run actually produced, shaped into a bounded blob the chat/client reads
to render the right-sidebar vision panel (asset id, model/provider, resolution,
detected text, observations, regions, confidence, chart/document/comparison
detail, provenance/security). It never fabricates a result: a failed analysis is
recorded as failed, and an empty run carries no blob.
"""

from __future__ import annotations

from typing import Any, Optional

MAX_VISIONS = 20
MAX_OBSERVATIONS = 60
MAX_TEXT_SPANS = 120
MAX_DESCRIPTION_CHARS = 4000


class VisionCollector:
    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []
        self._failures: list[dict[str, Any]] = []

    def add(self, result: Any) -> None:
        """Record one vision result (a `VisionResult` or its dict)."""
        try:
            payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        except Exception:  # noqa: BLE001 - collection must never break a run
            return
        if not isinstance(payload, dict):
            return
        if payload.get("ok") is False:
            if len(self._failures) < MAX_VISIONS:
                self._failures.append({
                    "mode": payload.get("mode"),
                    "error": payload.get("error"),
                })
            return
        if len(self._results) >= MAX_VISIONS:
            return
        self._results.append(_bounded(payload))

    def has_content(self) -> bool:
        return bool(self._results or self._failures)

    def to_blob(self) -> Optional[dict[str, Any]]:
        if not self.has_content():
            return None
        return {
            "type": "vision",
            "status": "collected",
            "count": len(self._results),
            "results": self._results,
            "failures": self._failures or None,
        }


def _bounded(payload: dict[str, Any]) -> dict[str, Any]:
    """Trim a vision-result dict to a bounded, UI-oriented shape."""
    observations = payload.get("observations") or []
    text = payload.get("text") or []
    chart = payload.get("chart")
    document = None
    provenance = payload.get("provenance") or {}
    if isinstance(provenance.get("document"), dict):
        document = provenance["document"]
    return {
        "ok": payload.get("ok", True),
        "mode": payload.get("mode"),
        "description": str(payload.get("description") or "")[:MAX_DESCRIPTION_CHARS],
        "assetId": payload.get("asset_id"),
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "backend": payload.get("backend"),
        "confidence": payload.get("confidence"),
        "latencyMs": payload.get("latency_ms"),
        "usage": payload.get("usage"),
        "cached": payload.get("cached", False),
        "observations": [
            {
                "text": o.get("text"),
                "kind": o.get("kind"),
                "method": o.get("method"),
                "confidence": o.get("confidence"),
                "region": o.get("region"),
            }
            for o in observations[:MAX_OBSERVATIONS] if isinstance(o, dict)
        ],
        "text": [
            {"text": t.get("text"), "bounds": t.get("bounds"), "confidence": t.get("confidence")}
            for t in text[:MAX_TEXT_SPANS] if isinstance(t, dict)
        ],
        "tables": payload.get("tables") or [],
        "chart": chart,
        "comparison": payload.get("comparison"),
        "document": document,
        "warnings": payload.get("warnings") or [],
        "provenance": {
            "source": provenance.get("source"),
            "question": provenance.get("question"),
            "security": provenance.get("security"),
            "fallback": provenance.get("fallback"),
        },
    }


__all__ = ["VisionCollector", "MAX_VISIONS"]
