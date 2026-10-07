"""Financial screen understanding.

Turns a snapshot's OCR/AX text into a structured `ObservedFinancialState` with
explicit screen-derived provenance. The result is NEVER treated as authoritative
market data: it carries `source_type = desktop_screen`, the application, the
window, the capture id, a confidence and the extraction method, so the evidence
layer can tell a screen reading apart from a provider/official source.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from ..models import ObservedFinancialState, Snapshot
from .fields import extract_fields


class FinancialExtractor:
    def __init__(self, *, min_confidence: float = 0.4) -> None:
        self._min_confidence = min_confidence

    def extract(
        self,
        *,
        snapshot: Snapshot,
        application: str = "",
        window: str = "",
        ocr_text: Optional[str] = None,
    ) -> ObservedFinancialState:
        text = ocr_text if ocr_text is not None else snapshot.text
        lines = [line for line in (text or "").splitlines() if line.strip()]
        # Strip the observation header line.
        lines = [line for line in lines if not line.startswith("[observation mode")]
        # Also mine element names/values (AX gives clean label→value pairs).
        for element in snapshot.elements:
            if element.name:
                combined = f"{element.name}: {element.value}" if element.value else element.name
                lines.append(combined)

        fields = extract_fields(lines)
        confidence = self._score(fields)
        method = "ocr" if snapshot.image_path else "accessibility"
        return ObservedFinancialState(
            application=application or snapshot.application,
            window=window or snapshot.window_title,
            symbol=fields.get("symbol"),
            fields={k: v for k, v in fields.items() if k != "symbol"},
            confidence=confidence, timestamp=time.time(),
            capture_id=snapshot.snapshot_id, extraction_method=method,
        )

    def _score(self, fields: dict[str, Any]) -> float:
        if not fields:
            return 0.0
        # A reading with a symbol plus several priced fields is more trustworthy.
        base = min(1.0, len(fields) / 6.0)
        if fields.get("symbol"):
            base += 0.15
        if any(k in fields for k in ("bid", "ask", "price")):
            base += 0.15
        return round(min(1.0, base), 2)

    def is_reliable(self, state: ObservedFinancialState) -> bool:
        return state.confidence >= self._min_confidence


__all__ = ["FinancialExtractor"]
