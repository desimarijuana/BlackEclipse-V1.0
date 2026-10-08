"""Vision → Evidence & Research Engine bridge.

Every visual observation that carries text can become an `Evidence` item in the
SAME `EvidenceStore` the web research engine uses, with full provenance
(asset id, region/bounding box, page, model, provider, method, timestamp,
confidence). This is how a visual claim can flow into citation and verification
without losing where it came from.

It does not fork the evidence contract: it builds the existing
`research.web_contracts.Evidence` object and persists it through
`EvidenceStore.save_evidence`.
"""

from __future__ import annotations

from typing import Any, Optional

from .contracts import VisionResult

#: How many observations one result may contribute as evidence (bounded writes).
MAX_EVIDENCE_PER_RESULT = 50


def _image_source_url(asset_id: Optional[str], source_ref: Optional[str]) -> str:
    """A stable, honest source URL for an image artifact."""
    if source_ref and isinstance(source_ref, str) and source_ref[:8].lower().startswith(("http://", "https://")):
        return source_ref
    if source_ref and isinstance(source_ref, str) and source_ref:
        # A local path / pseudo-ref: normalize to a URI so it is a valid URL.
        if "://" not in source_ref:
            return f"image://{source_ref.replace(chr(92), '/')}"
        return source_ref
    return f"image://{asset_id or 'unknown'}"


def record_result_evidence(
    store: Any,
    result: VisionResult,
    *,
    research_id: Optional[str] = None,
    source_ref: Optional[str] = None,
) -> list[str]:
    """Persist a vision result's observations as evidence. Returns evidence ids.

    A failure result contributes nothing. Observations without text are skipped
    (there is nothing to cite). A storage error is swallowed — evidence recording
    must never break a vision call.
    """
    if store is None or not result.ok:
        return []
    try:
        from ..research.web_contracts import Evidence, content_hash, evidence_id, source_id  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []

    url = _image_source_url(result.asset_id, source_ref or result.provenance.get("sourceRef"))
    sid = source_id(url)
    try:
        store.save_source({
            "sourceId": sid, "canonicalUrl": url, "domain": "image",
            "publisher": result.provider, "sourceType": "unknown",
            "retrievedAt": result.provenance.get("retrievedAt"),
            "contentHash": result.asset_id,
        }, research_id=research_id)
    except Exception:  # noqa: BLE001
        pass

    ids: list[str] = []
    observations = list(result.observations) + list(result.regions)
    # Deduplicate by text so an observation surfaced in both lists is not doubled.
    seen: set[str] = set()
    for obs in observations[:MAX_EVIDENCE_PER_RESULT]:
        text = (obs.text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        page = None
        prov = obs.details or {}
        if isinstance(result.provenance.get("document"), dict):
            page = result.provenance["document"].get("page")
        try:
            ev = Evidence(
                evidenceId=evidence_id(source_url=url, raw_text=text, page=page),
                sourceId=sid,
                sourceUrl=url,
                sourceType="unknown",
                publisher=result.provider,
                page=page,
                rawText=text,
                contentHash=content_hash(text),
                confidence=obs.confidence,
                contentTrust="UNTRUSTED",
                provenance={
                    "assetId": result.asset_id,
                    "model": result.model,
                    "provider": result.provider,
                    "backend": result.backend,
                    "method": obs.method,
                    "kind": obs.kind,
                    "bbox": obs.region.to_list() if obs.region else None,
                    "visionMode": result.mode,
                    "trust": "vision-observed",
                    "details": prov,
                },
            )
            store.save_evidence(ev.model_dump(), research_id=research_id)
            ids.append(ev.evidenceId)
        except Exception:  # noqa: BLE001 - one bad observation must not stop the rest
            continue
    return ids


__all__ = ["record_result_evidence", "MAX_EVIDENCE_PER_RESULT"]
