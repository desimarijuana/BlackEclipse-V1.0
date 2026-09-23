"""Durable research receipt (Phase 4, Milestone 7).

A receipt is a bounded, queryable record explaining what was requested, what was
retrieved, what was missing or disputed, which claims were linked to evidence,
what validation rejected, whether a repair ran, and why the final status is
`accepted`, `partial` or `rejected`.

It is persisted in `agent-memory.db` (additive table `ResearchReceipt`, created
idempotently), never in `eclipse-memory.db` and never in JDdS. No secrets are
stored, and source documents are kept bounded (hashes/summaries, not full text).
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from .mandate import ResearchMandate

RECEIPT_SCHEMA_VERSION = "1.0.0"


class EvidenceRef(BaseModel):
    """A bounded reference to one evidence item (no full source document)."""

    id: str
    kind: str
    source: Optional[str] = None
    sourceType: Optional[str] = None
    url: Optional[str] = None
    hash: Optional[str] = None
    summary: Optional[str] = None


class ResearchReceipt(BaseModel):
    runId: str
    schemaVersion: str = RECEIPT_SCHEMA_VERSION
    mandateVersion: str = "1.0.0"
    taskType: str = "general"
    objective: str = ""
    identityDecisions: list[dict[str, Any]] = Field(default_factory=list)
    retrievalRequests: list[dict[str, Any]] = Field(default_factory=list)
    evidenceRefs: list[EvidenceRef] = Field(default_factory=list)
    temporalStatus: Optional[dict[str, Any]] = None
    coverage: list[dict[str, Any]] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    validationIssues: list[str] = Field(default_factory=list)
    repair: Optional[dict[str, Any]] = None
    finalStatus: str = "rejected"
    provider: Optional[str] = None
    model: Optional[str] = None
    createdAt: Optional[str] = None


def build_receipt(
    run_id: str,
    mandate: ResearchMandate,
    *,
    coverage: Any = None,
    validation: Any = None,
    evidence: Optional[list[Any]] = None,
    retrieval_requests: Optional[list[dict[str, Any]]] = None,
    repair: Optional[dict[str, Any]] = None,
    final_status: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    as_of: Optional[str] = None,
) -> ResearchReceipt:
    """Assemble a receipt from the run's decision objects.

    `finalStatus` defaults to the validation status (which already folds in
    coverage); it is never optimistically set to `accepted`.
    """
    evidence = evidence or []

    refs = [
        EvidenceRef(
            id=getattr(item, "id", ""),
            kind=getattr(item, "kind", "unknown"),
            source=getattr(getattr(item, "source", None), "source", None),
            sourceType=getattr(getattr(item, "source", None), "sourceType", None),
            url=getattr(getattr(item, "source", None), "url", None),
            hash=str(abs(hash(str(getattr(item, "id", ""))))) ,
            summary=(getattr(item, "summary", "") or "")[:240],
        )
        for item in evidence
    ]

    claims: list[dict[str, Any]] = []
    validation_issues: list[str] = []
    if validation is not None:
        for claim in getattr(validation, "claims", []) or []:
            claims.append(
                {
                    "text": claim.text[:300],
                    "kind": claim.kind,
                    "supportStatus": claim.supportStatus,
                    "evidenceIds": claim.evidenceIds,
                    "calculationId": claim.calculationId,
                    "issues": claim.issues,
                }
            )
            validation_issues.extend(claim.issues)
        validation_issues.extend(getattr(validation, "unresolved", []) or [])

    coverage_rows: list[dict[str, Any]] = []
    if coverage is not None:
        for leg in getattr(coverage, "legs", []) or []:
            coverage_rows.append(
                {
                    "legId": leg.legId,
                    "metric": leg.metric,
                    "period": leg.period,
                    "basis": leg.basis,
                    "status": leg.status,
                    "evidenceIds": leg.evidenceIds,
                }
            )

    identity_decisions = [
        {
            "raw": entity.raw,
            "symbol": entity.symbol,
            "market": entity.market,
            "canonical": entity.canonical,
            "ambiguous": entity.ambiguous,
            "reason": entity.reason,
        }
        for entity in mandate.entities
    ]

    status = final_status
    if status is None:
        status = getattr(validation, "status", None) or getattr(coverage, "status", None) or "rejected"

    return ResearchReceipt(
        runId=run_id,
        taskType=mandate.taskType,
        objective=mandate.objective,
        identityDecisions=identity_decisions,
        retrievalRequests=retrieval_requests or [],
        evidenceRefs=refs,
        temporalStatus={
            "asOf": as_of or mandate.asOf,
            "timezone": mandate.timezone,
        } if (as_of or mandate.asOf or mandate.timezone) else None,
        coverage=coverage_rows,
        claims=claims,
        validationIssues=sorted(set(validation_issues))[:50],
        repair=repair,
        finalStatus=status,
        provider=provider,
        model=model,
    )


__all__ = ["RECEIPT_SCHEMA_VERSION", "EvidenceRef", "ResearchReceipt", "build_receipt"]
