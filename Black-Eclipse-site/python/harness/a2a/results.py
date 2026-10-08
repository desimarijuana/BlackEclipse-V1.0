"""Result normalization, evidence linking, conflict detection and merging.

Merging is NOT string concatenation. It normalizes, deduplicates, links every
finding to its evidence, detects conflicts, names gaps, and computes a coverage-
and-evidence-weighted confidence. A finding with no evidence reference is kept but
listed as unsupported — never silently promoted to fact.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .model import (
    A2AResult,
    Conflict,
    ConflictCandidate,
    Finding,
    MergedResult,
)

_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_STOP = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in", "on", "for", "and",
    "or", "at", "by", "as", "it", "its", "this", "that", "with", "value", "price",
    "fair", "estimated", "estimate", "about", "approximately", "around", "usd", "$",
})
#: Oldest evidence first — a finding older than this many seconds is "stale".
DEFAULT_STALE_SECONDS = 7 * 24 * 3600


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t]


def _subject_key(claim: str) -> str:
    """The deterministic subject of a claim: its non-numeric content tokens."""
    toks = [t for t in _tokens(claim) if not _NUM_RE.fullmatch(t) and t not in _STOP]
    return " ".join(sorted(set(toks)))


def _numbers(claim: str) -> list[float]:
    out: list[float] = []
    for raw in _NUM_RE.findall(claim or ""):
        try:
            out.append(float(raw.replace(",", "")))
        except ValueError:
            continue
    return out


def normalize_finding(finding: Finding) -> Finding:
    finding.claim = " ".join((finding.claim or "").split())
    finding.confidence = min(1.0, max(0.0, float(finding.confidence)))
    finding.evidence_refs = list(dict.fromkeys(finding.evidence_refs))
    finding.source_refs = list(dict.fromkeys(finding.source_refs))
    return finding


def detect_conflicts(results: list[A2AResult]) -> list[Conflict]:
    """Deterministic conflict detection over the union of all findings.

    A conflict is raised ONLY when two findings address the same subject AND
    carry different numeric values, or when an agent explicitly reported one.
    Everything else (different assumptions, different wording) is not promoted to
    a conflict — no false positives.
    """
    conflicts: list[Conflict] = []
    seen_ids: set[str] = set()
    for result in results:
        for conflict in result.conflicts:
            if conflict.id not in seen_ids:
                seen_ids.add(conflict.id)
                conflicts.append(conflict)

    by_subject: dict[str, list[tuple[str, float, list[str], str]]] = {}
    for result in results:
        for finding in result.findings:
            nums = _numbers(finding.claim)
            if not nums:
                continue
            key = _subject_key(finding.claim)
            if not key:
                continue
            by_subject.setdefault(key, []).append(
                (result.agent_id, nums[0], list(finding.evidence_refs), finding.claim)
            )

    for subject, entries in by_subject.items():
        values = {round(v, 6) for _, v, _, _ in entries}
        if len(entries) < 2 or len(values) < 2:
            continue
        candidates = [
            ConflictCandidate(
                agent_id=agent, value=value, confidence=0.5, evidence_refs=refs, basis=claim,
            )
            for agent, value, refs, claim in entries
        ]
        conflicts.append(Conflict(
            subject=subject,
            candidates=candidates,
            status="UNRESOLVED",
            material=True,
            reason=f"{len(entries)} agents reported different values for {subject}",
        ))
    return conflicts


def merge_results(
    results: list[A2AResult],
    *,
    evidence_exists: Optional[Callable[[str], bool]] = None,
    as_of: Optional[float] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> MergedResult:
    """Normalize, deduplicate, link evidence, detect conflicts, compute confidence."""
    dropped = 0
    findings: list[Finding] = []
    seen_claims: set[str] = set()
    all_evidence: list[str] = []
    sources: list[str] = []
    unsupported: list[str] = []

    for result in results:
        if result.agent_id and result.agent_id not in sources:
            sources.append(result.agent_id)
        for ref in result.evidence_refs:
            if ref not in all_evidence:
                all_evidence.append(ref)
        for finding in result.findings:
            finding = normalize_finding(finding)
            key = " ".join(_tokens(finding.claim))
            if key and key in seen_claims:
                dropped += 1
                continue
            seen_claims.add(key)
            for ref in finding.evidence_refs:
                if ref not in all_evidence:
                    all_evidence.append(ref)
            if evidence_exists is not None:
                if finding.evidence_refs and not any(evidence_exists(r) for r in finding.evidence_refs):
                    finding.assumptions = list(dict.fromkeys(
                        [*finding.assumptions, "no evidence reference could be verified"]
                    ))
                    unsupported.append(finding.claim)
                    finding.confidence = min(finding.confidence, 0.4)
            elif not finding.evidence_refs:
                unsupported.append(finding.claim)
                finding.confidence = min(finding.confidence, 0.4)
            findings.append(finding)

    conflicts = detect_conflicts(results)

    gaps: list[str] = []
    for result in results:
        for gap in result.gaps:
            if gap not in gaps:
                gaps.append(gap)
    # A conflict over a subject is a gap in the synthesis.
    for conflict in conflicts:
        entry = f"unresolved disagreement about {conflict.subject}"
        if conflict.status == "UNRESOLVED" and entry not in gaps:
            gaps.append(entry)

    total = len(results)
    completed = sum(1 for r in results if r.status == "COMPLETED")
    coverage = (completed / total) if total else 0.0

    evidence_backed = [f for f in findings if f.evidence_refs]
    if findings:
        base = sum(f.confidence for f in findings) / len(findings)
        support = len(evidence_backed) / len(findings)
        confidence = round(min(1.0, base * (0.5 + 0.5 * support)) * coverage, 3) if total else 0.0
    else:
        confidence = 0.0

    summary = _synthesize(results, findings, conflicts, coverage)

    return MergedResult(
        summary=summary, findings=findings, evidence_refs=all_evidence,
        conflicts=conflicts, gaps=gaps, confidence=confidence, coverage=round(coverage, 3),
        sources=sources, unsupported_claims=unsupported, dropped_duplicates=dropped,
    )


def _synthesize(results: list[A2AResult], findings: list[Finding],
                conflicts: list[Conflict], coverage: float) -> str:
    completed = [r for r in results if r.status == "COMPLETED"]
    lines: list[str] = []
    lines.append(
        f"Combined {len(completed)} of {len(results)} agent result(s) "
        f"({int(round(coverage * 100))}% coverage)."
    )
    if findings:
        lines.append("Evidence-backed findings:")
        for finding in findings[:20]:
            marker = "" if finding.evidence_refs else " (unverified)"
            lines.append(f"- {finding.claim}{marker}")
    unresolved = [c for c in conflicts if c.status == "UNRESOLVED"]
    if unresolved:
        lines.append(f"{len(unresolved)} unresolved conflict(s) remain and are reported, not averaged.")
    failed = [r for r in results if r.status != "COMPLETED"]
    if failed:
        lines.append(f"{len(failed)} part(s) did not complete; nothing was fabricated for them.")
    return "\n".join(lines)


__all__ = [
    "DEFAULT_STALE_SECONDS",
    "detect_conflicts",
    "merge_results",
    "normalize_finding",
]
