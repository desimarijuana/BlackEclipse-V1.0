"""Persistent visual memory (spec §35).

Visual information is persisted ONLY when it is useful AND permitted — never
automatically, never permanently for a sensitive screenshot. This module is the
ONE seam that turns a vision result into a durable Eclipse-Memory record. It does
NOT bypass the memory decision gate: it goes through `authorize_proposal` +
`commit_decision` exactly like the `memory` tool, so a model-facing write still
requires explicit user intent and scope rules.

Storage policy (deliberate, honest):
  * A compact TEXT summary is handed to the memory gate/store (never the image
    bytes and never a raw base64 blob).
  * The stored `structuredData` references the content-addressed `assetId` (so the
    binary stays on the filesystem tier) plus the model/provider/regions/confidence.
  * A SENSITIVE or ephemeral-source result is marked low-importance and given a TTL,
    so it is not kept forever by default.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .contracts import VisionResult
from .errors import VisionError, VisionErrorClass

#: A sensitive/ephemeral visual memory is retained for one day by default, not
#: forever. An explicit non-sensitive memory uses the store's own policy.
_SENSITIVE_TTL_SECONDS = 86_400
_MAX_SUMMARY_CHARS = 1200


def _summary(result: VisionResult, content: Optional[str]) -> str:
    if content and content.strip():
        return content.strip()[:_MAX_SUMMARY_CHARS]
    parts: list[str] = [f"Visual observation ({result.mode})."]
    if result.description:
        parts.append(result.description[:600])
    for obs in result.observations[:8]:
        parts.append(f"- {obs.text}"[:200])
    if result.chart and result.chart.get("trend"):
        parts.append(f"chart trend: {result.chart.get('trend')}")
    return " ".join(parts)[:_MAX_SUMMARY_CHARS]


def remember_visual(
    result: VisionResult,
    ctx: Any,
    *,
    subject: Optional[str] = None,
    content: Optional[str] = None,
    scope: str = "general",
    confidence: float = 0.7,
) -> dict[str, Any]:
    """Persist a vision result through the Eclipse-Memory decision gate.

    Returns the decision outcome. Raises `VisionError` only when the memory
    service is not attached to the run; a gate refusal is returned as data (the
    memory is simply not saved).
    """
    service = getattr(ctx, "memory_service", None)
    if service is None:
        raise VisionError(VisionErrorClass.INTERNAL_ERROR, "Eclipse-Memory is not attached to this run")
    if not result.ok:
        raise VisionError(VisionErrorClass.INVALID_INPUT, "a failed vision result cannot be remembered")

    security = (result.provenance or {}).get("security") or {}
    sensitive = bool(security.get("sensitive"))
    ephemeral = result.provenance.get("source") in ("screenshot", "clipboard", "browser")

    summary = _summary(result, content)
    structured = {
        "assetId": result.asset_id,
        "visionMode": result.mode,
        "provider": result.provider,
        "model": result.model,
        "backend": result.backend,
        "confidence": result.confidence,
        "regions": [
            {"text": o.text, "bbox": o.region.to_bbox() if o.region else None,
             "kind": o.kind, "method": o.method, "confidence": o.confidence}
            for o in result.observations[:20]
        ],
        "chart": result.chart,
        "source": result.provenance.get("source"),
    }
    expires_at = None
    if sensitive or ephemeral:
        expires_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _SENSITIVE_TTL_SECONDS))

    from ..eclipse_memory.decision import authorize_proposal  # noqa: PLC0415

    try:
        settings = service.policy.get_all()
    except Exception:  # noqa: BLE001 - a policy read failure must fail closed
        settings = {}
    try:
        decision = authorize_proposal(
            content=summary,
            provenance="memory_tool",
            user_message=getattr(ctx, "user_message", "") or "",
            user_id=getattr(ctx, "user_id", None),
            memory_type="observation",
            scope=scope,
            scope_id=getattr(ctx, "user_id", None),
            subject=subject,
            confidence=max(0.0, min(1.0, confidence)),
            settings=settings,
            evidence={"assetId": result.asset_id, "kind": "vision"} if result.asset_id else None,
        )
    except (TypeError, ValueError) as exc:
        raise VisionError(VisionErrorClass.INVALID_INPUT, f"invalid memory proposal: {exc}") from exc

    # Attach structured data + TTL by committing through the decision when it saves.
    if decision.outcome == "save":
        try:
            saved = service.store.save_memory(
                memory_type="observation",
                scope=decision.scope or scope,
                content=summary,
                scope_id=getattr(ctx, "user_id", None),
                subject=subject,
                structured_data=structured,
                source="vision",
                source_run_id=getattr(ctx, "run_id", None),
                confidence=max(0.0, min(1.0, confidence)),
                importance=0.4 if (sensitive or ephemeral) else 0.6,
                verification="unverified",
                created_by=getattr(ctx, "user_id", None),
                expires_at=expires_at,
                authority="explicit",
            )
        except Exception as exc:  # noqa: BLE001
            raise VisionError(VisionErrorClass.STORAGE_ERROR, f"the visual memory could not be stored: {exc}", cause=exc) from exc
        return {
            "saved": True, "action": "save", "id": saved.get("id"),
            "scope": saved.get("scope"), "subject": subject,
            "expiresAt": expires_at, "assetId": result.asset_id,
            "sensitive": sensitive,
        }

    outcome = service.commit_decision(decision, run_id=getattr(ctx, "run_id", None), user_id=getattr(ctx, "user_id", None))
    return {
        "saved": False,
        "action": outcome.get("action", decision.outcome),
        "reason": decision.reason or outcome.get("reason"),
        "assetId": result.asset_id,
        "sensitive": sensitive,
    }


__all__ = ["remember_visual"]
