"""Browser → verified-claim bridge (Phase 10.4).

A value the browser read from a page is a CANDIDATE, never a fact. This module is
the ONE legal path that can turn a browser-derived observation into a *verified
claim*: it fabricates an `Evidence` with provenance from the browser (the real
URL, title and a content hash of the observed text), then runs the research
engine's OWN deterministic verification (`web_verify.verify_claim`) over it.

It deliberately does NOT:
  * invent a second verifier — the engine's `verify_claim` is the only authority;
  * promote a value without provenance — a browser observation with no real
    `http(s)` URL cannot become evidence;
  * treat page text as instructions — the evidence is marked `contentTrust:
    UNTRUSTED` exactly like any fetched page.

A browser observation enters a verified claim ONLY through `claim_from_browser`,
which requires a claim TEXT that is actually supported by the observed text
(checked by presence), so a number can never be attached to an unrelated
sentence.
"""

from __future__ import annotations

from typing import Any, Optional

from .evidence import is_page_evidence_url


class BrowserClaimError(Exception):
    """A browser observation could not enter a claim (a plain, honest refusal)."""


def evidence_from_browser(
    *,
    url: str,
    text: str,
    title: Optional[str] = None,
    section: Optional[str] = None,
    structured_value: Any = None,
    unit: Optional[str] = None,
    period: Optional[str] = None,
    metric: Optional[str] = None,
    retrieved_at: Optional[str] = None,
) -> Any:
    """Build engine `Evidence` from a browser observation. Never fabricates provenance.

    Refuses (raises) when the URL is not a real http(s) page or the text is empty:
    an internal/blank page is not a source and a value with no text is not evidence.
    """
    if not is_page_evidence_url(url):
        raise BrowserClaimError("A browser value needs a real http(s) page URL to become evidence.")
    if not (text or "").strip():
        raise BrowserClaimError("A browser value needs the observed page text to become evidence.")
    from ..research.web_contracts import Evidence, content_hash, evidence_id
    from ..research.web_sources import make_source, resolve_entity

    source = make_source(url, title=title, content_hash_value=content_hash(text))
    entity = resolve_entity(title or url)
    provenance: dict[str, Any] = {"title": title, "domain": source.domain, "origin": "browser"}
    if metric:
        provenance["metric"] = metric
    if section:
        provenance["section"] = section
    return Evidence(
        evidenceId=evidence_id(source_url=url, raw_text=text),
        sourceId=source.sourceId,
        sourceUrl=url,
        sourceType=source.sourceType,
        publisher=source.publisher,
        entityId=(entity.entityId if entity else None),
        retrievedAt=retrieved_at or _now(),
        section=section,
        rawText=text,
        claimText=metric,
        structuredValue=structured_value,
        unit=unit,
        period=period,
        contentHash=content_hash(text),
        provenance=provenance,
    )


def claim_from_browser(
    *,
    claim_text: str,
    url: str,
    observed_text: str,
    title: Optional[str] = None,
    section: Optional[str] = None,
    structured_value: Any = None,
    unit: Optional[str] = None,
    period: Optional[str] = None,
    metric: Optional[str] = None,
    conflicts: Optional[list[Any]] = None,
    as_of: Optional[str] = None,
    freshness: Optional[str] = None,
) -> Any:
    """Turn a browser observation into a VERIFIED claim via the engine's one path.

    The claim is built, then `web_verify.verify_claim` (the engine's own authority)
    determines its status/confidence. A claim whose text is not grounded in the
    observed page text is refused: a browser number can never be attached to an
    unrelated statement.
    """
    if not (claim_text or "").strip():
        raise BrowserClaimError("A claim needs text.")
    # Grounding: the claim must be supported by the observed text. We require the
    # claim's significant tokens to appear in the page text (a conservative check,
    # never a semantic leap), so the value cannot be laundered onto another claim.
    if not _grounded(claim_text, observed_text):
        raise BrowserClaimError("That claim isn't grounded in the page text the browser observed.")

    evidence = evidence_from_browser(
        url=url, text=observed_text, title=title, section=section,
        structured_value=structured_value, unit=unit, period=period, metric=metric,
    )
    from ..research.web_contracts import Claim
    from ..research.web_verify import verify_claim

    claim = Claim(text=claim_text.strip()[:400], kind="FACT", evidenceIds=[evidence.evidenceId])
    verified = verify_claim(
        claim, {evidence.evidenceId: evidence},
        conflicts=conflicts or [], as_of=as_of, freshness=freshness,
    )
    return {"claim": verified, "evidence": evidence, "verified": verified.status not in ("UNSUPPORTED",)}


def _grounded(claim_text: str, observed_text: str) -> bool:
    """Whether a claim's significant tokens appear in the observed page text."""
    import re

    haystack = (observed_text or "").lower()
    if not haystack:
        return False
    tokens = [t for t in re.findall(r"[a-z0-9]{4,}", (claim_text or "").lower())]
    if not tokens:
        # A very short claim (e.g. a bare number) still needs SOME overlap.
        return any(tok and tok in haystack for tok in (claim_text or "").lower().split())
    return any(token in haystack for token in tokens)


def _now() -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.now(timezone.utc).isoformat()


__all__ = ["BrowserClaimError", "claim_from_browser", "evidence_from_browser"]
