"""MCP-aware source planning (Phase 6, Milestone 6).

MCP becomes a first-class *candidate* for native retrieval planning when an
operator has declared a selected MCP tool to be a data source. A generic MCP tool
that does not implement the contract stays directly callable by the model — it is
**not** forced through the contract and is never withheld for not implementing it.

This module provides the planning primitives (kept pure and testable so they do
not require a live MCP server):

  * `SourceCandidate` — a normalized, provider-independent evidence source with an
    observation time, freshness state and verification state.
  * `SourceFreshness` — three DISTINCT states: `fresh`, `stale`, `missing`, plus
    `failed` and `unavailable`. They are never collapsed into "no data".
  * `plan_candidates` — prefers the fresher ELIGIBLE source and **preserves a
    conflict** (two eligible sources disagreeing) rather than silently choosing.
  * `build_mcp_retrieval_source` — an adapter implementing the native
    `RetrievalSource` protocol for a declared MCP tool.

An MCP result is always `external` / `eclipseVerified=False`. JDdS is never
silently upgraded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Freshness states. `stale` (usable but old) is distinct from `missing` (never
# had it) and from `failed` (tried and errored).
FRESH = "fresh"
STALE = "stale"
MISSING = "missing"
FAILED = "failed"
UNAVAILABLE = "unavailable"

# Default TTL by data type (seconds) when the operator does not override.
DEFAULT_TTL_SECONDS: dict[str, int] = {
    "current_quote": 60,
    "historical_prices": 24 * 60 * 60,
    "company_profile": 7 * 24 * 60 * 60,
    "financial_statements": 24 * 60 * 60,
    "earnings": 6 * 60 * 60,
    "macro_series": 24 * 60 * 60,
    "news": 15 * 60,
    "web_research": 60 * 60,
}


def freshness_state(*, age_seconds: Optional[float], ttl_seconds: int) -> str:
    """Classify an observation's freshness. `None` age means it never arrived."""
    if age_seconds is None:
        return MISSING
    if ttl_seconds <= 0:
        return FRESH
    return FRESH if age_seconds <= ttl_seconds else STALE


@dataclass
class SourceCandidate:
    """One eligible source's answer for a datum, with provider-independent provenance."""

    source_id: str                    # "JDDS", "WEB", "MCP:<server>:<tool>", ...
    kind: str                         # "jds" | "web" | "mcp" | "provider"
    verification: str                 # "jds" | "external" | ...
    eclipse_verified: bool
    value: Any = None
    observed_at: Optional[float] = None   # epoch seconds, or None if unknown
    retrieved_at: Optional[float] = None
    age_seconds: Optional[float] = None
    freshness: str = MISSING
    status: str = "OK"                # OK | UNAVAILABLE | ERROR
    detail: Optional[str] = None
    raw: Optional[Any] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        return {
            "sourceId": self.source_id,
            "kind": self.kind,
            "verification": self.verification,
            "eclipseVerified": self.eclipse_verified,
            "value": self.value,
            "observedAt": self.observed_at,
            "retrievedAt": self.retrieved_at,
            "freshness": self.freshness,
            "status": self.status,
            "detail": self.detail,
            "metadata": self.metadata,
        }


@dataclass
class PlanResult:
    chosen: Optional[SourceCandidate]
    considered: list[SourceCandidate] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    explanation: str = ""
    missing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "chosen": self.chosen.public() if self.chosen else None,
            "considered": [c.public() for c in self.considered],
            "conflicts": list(self.conflicts),
            "explanation": self.explanation,
            "missing": list(self.missing),
            "failed": list(self.failed),
        }


def _numeric(value: Any) -> Optional[float]:
    return float(value) if isinstance(value, (int, float)) else None


def plan_candidates(
    candidates: list[SourceCandidate],
    *,
    rel_tolerance: float = 0.005,
) -> PlanResult:
    """Prefer the fresher eligible source; preserve conflicts; never fabricate.

    - A `failed` candidate is reported separately and never chosen.
    - A `missing` candidate is reported as missing.
    - Among OK candidates, prefer `fresh` over `stale`; ties broken by higher
      tier (jds/provider over external) — but a conflict (a real numeric
      disagreement) is PRESERVED, not resolved away.
    """
    ok = [c for c in candidates if c.status == "OK" and c.freshness in (FRESH, STALE)]
    failed = [c.source_id for c in candidates if c.status == "ERROR" or c.freshness == FAILED]
    missing = [c.source_id for c in candidates if c.freshness == MISSING]

    if not ok:
        reason = "no eligible source returned a value"
        if failed:
            reason += f"; failed: {', '.join(failed)}"
        return PlanResult(None, candidates, [], reason, missing, failed)

    fresh = [c for c in ok if c.freshness == FRESH]
    pool = fresh or ok
    # Deterministic preference: higher trust tier, then more recent observation.
    def _rank(c: SourceCandidate) -> tuple[int, float]:
        tier = 2 if c.kind in ("jds", "provider") else 1
        return (tier, c.observed_at or 0.0)

    chosen = max(pool, key=_rank)
    others = [c for c in pool if c is not chosen and _numeric(c.value) is not None and _numeric(chosen.value) is not None]
    conflicts: list[dict[str, Any]] = []
    for other in others:
        a, b = _numeric(chosen.value), _numeric(other.value)
        if a is None or b is None:
            continue
        denom = max(abs(a), abs(b), 1e-9)
        if abs(a - b) / denom > rel_tolerance:
            conflicts.append({
                "metric": chosen.metadata.get("metric") or chosen.metadata.get("symbol"),
                "values": [chosen.public(), other.public()],
                "note": "sources disagree; both values preserved, neither silently chosen",
            })

    explanation = f"chose {chosen.source_id} ({chosen.freshness})"
    if conflicts:
        explanation += f"; {len(conflicts)} conflict(s) preserved"
    if not fresh and ok:
        explanation += "; no fresh source available, using the freshest stale source"
    return PlanResult(chosen, candidates, conflicts, explanation, missing, failed)


def build_mcp_retrieval_source(
    *,
    manager: Any,
    server_id: str,
    tool_name: str,
    data_type: str,
    ttl_seconds: Optional[int] = None,
) -> Any:
    """An adapter implementing the native `RetrievalSource` for a declared MCP tool.

    Only a tool the operator has explicitly declared as a data source is adapted;
    a generic MCP tool is left directly callable and never withheld. The result is
    always `secondary` tier, `eclipseVerified=False` — a JDdS result is never
    silently upgraded and an MCP result is never claimed as Eclipse-verified.
    """
    from ..retrieval.contract import (
        EvidenceItem,
        NormalizedFinancialObject,
        SourceReference,
    )
    from ..retrieval.sources import SourceOutcome

    source_id = f"MCP:{server_id}:{tool_name}"
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_TTL_SECONDS.get(data_type, 60 * 60)

    def _reference() -> SourceReference:
        return SourceReference(
            source=source_id,
            sourceType="secondary",
            retrievedAt=_now_iso(),
            validationStatus="unverified",
        )

    def _numeric_from(data: Any) -> Optional[float]:
        if isinstance(data, (int, float)):
            return float(data)
        if isinstance(data, dict):
            for key in ("value", "price", "close", "last", "amount"):
                v = data.get(key)
                if isinstance(v, (int, float)):
                    return float(v)
        return None

    class _McpRetrievalSource:
        name = source_id
        tier = "secondary"
        dataTypes = (data_type,)

        def available(self, request: Any) -> bool:
            rt = getattr(manager, "_runtimes", {}).get(server_id)
            return bool(rt and rt.config.enabled and rt.state == "connected")

        async def retrieve(self, request: Any) -> SourceOutcome:
            rt = getattr(manager, "_runtimes", {}).get(server_id)
            if rt is None or rt.connection is None or rt.state != "connected":
                return SourceOutcome(source=self.name, status="UNAVAILABLE",
                                     error="MCP server is not connected")
            symbol = getattr(request, "instrument", None) or getattr(request, "symbol", "") or getattr(request, "objective", "")
            arguments: dict[str, Any] = {}
            if symbol:
                arguments["symbol"] = symbol
            if getattr(request, "dateRange", None):
                arguments["dateRange"] = getattr(request, "dateRange")
            try:
                outcome = await rt.connection.call_tool(
                    tool_name, arguments, timeout_ms=rt.limits["callTimeoutMs"]
                )
            except Exception as exc:  # noqa: BLE001 - a provider failure is data
                return SourceOutcome(source=self.name, status="ERROR", error=rt.redact(str(exc)))

            reference = _reference()
            if not outcome.ok:
                return SourceOutcome(
                    source=self.name, status="ERROR", error="MCP reported an error",
                    references=[reference],
                )
            raw_value = _numeric_from((outcome.data or {}).get("structuredContent"))
            if raw_value is None:
                raw_value = _numeric_from(outcome.data)
            obj = NormalizedFinancialObject(
                name="value",
                value=raw_value,
                instrument=str(symbol) or None,
                source=reference,
                freshness="any",
                quality="unknown",
                raw={"text": outcome.text, "data": outcome.data},
            )
            evidence = EvidenceItem(
                id=f"{source_id}:{symbol}",
                kind="unverified",
                summary=(outcome.text or "")[:500],
                data=outcome.data,
                objects=[obj],
                source=reference,
                quality="unknown",
                warnings=["External MCP source: not Eclipse-verified."],
            )
            return SourceOutcome(
                source=self.name,
                status="OK",
                objects=[obj],
                references=[reference],
                evidence=[evidence],
                raw={"text": outcome.text, "data": outcome.data},
            )

    return _McpRetrievalSource()


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "SourceCandidate",
    "PlanResult",
    "plan_candidates",
    "freshness_state",
    "build_mcp_retrieval_source",
    "DEFAULT_TTL_SECONDS",
    "FRESH",
    "STALE",
    "MISSING",
    "FAILED",
    "UNAVAILABLE",
]
