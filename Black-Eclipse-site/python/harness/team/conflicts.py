"""Evidence-based conflict detection and reconciliation for a team run.

Deterministic by default. Two findings about the same subject that disagree are
NEVER reconciled by voting, by averaging incompatible numbers, by trusting the
newest source, or by inventing evidence. Instead the disagreement is classified:
a benign cause (a different period, unit, currency, accounting basis, an
estimate-vs-reported figure, or stale data) EXPLAINS it; anything else stays
UNRESOLVED and is disclosed. An optional investigator (targeted research or an
independent reviewer) may resolve a genuine conflict, and its name + evidence
are recorded — never a fabricated value.

Original findings and their provenance are preserved; reconciliation only ever
annotates conflicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .model import (
    ConflictKind,
    ConflictStatus,
    TeamConflict,
    TeamFinding,
    new_conflict_id,
)

_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "of", "for", "to", "in", "on",
    "at", "by", "as", "and", "or", "with", "value", "price", "total", "figure",
    "reported", "estimated", "estimate", "usd", "eur", "gbp", "%", "per", "share",
}
_TOLERANCE = 0.005            # 0.5% relative — identical to the research engine
DEFAULT_STALE_SECONDS = 7 * 24 * 3600


@dataclass
class ReconcileResult:
    """The outcome of reconciling a set of findings."""

    conflicts: list[TeamConflict] = field(default_factory=list)
    supported: list[TeamFinding] = field(default_factory=list)
    unsupported: list[TeamFinding] = field(default_factory=list)

    @property
    def unresolved(self) -> list[TeamConflict]:
        return [c for c in self.conflicts if c.status is ConflictStatus.UNRESOLVED]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflicts": [c.model_dump(by_alias=True) for c in self.conflicts],
            "unresolved": [c.model_dump(by_alias=True) for c in self.unresolved],
            "supportedFindingIds": [f.id for f in self.supported],
            "unsupportedFindingIds": [f.id for f in self.unsupported],
        }


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+", text.lower())
        if token not in _STOP and not token.isdigit()
    }


def subject_of(finding: TeamFinding | dict[str, Any]) -> str:
    """The deterministic subject key of a finding (its claim minus numbers/stopwords)."""
    claim = finding.claim if isinstance(finding, TeamFinding) else str(finding.get("claim") or "")
    tokens = sorted(_tokens(claim))
    return " ".join(tokens) or claim.strip().lower()[:120]


def _numbers(finding: TeamFinding) -> list[float]:
    if finding.value is not None:
        return [float(finding.value)]
    return [float(n.replace(",", "")) for n in _NUM_RE.findall(finding.claim)]


def _values_agree(a: float, b: float) -> bool:
    if a == b:
        return True
    scale = max(abs(a), abs(b)) or 1.0
    return abs(a - b) / scale <= _TOLERANCE


def _is_stale(finding: TeamFinding, *, now_epoch: float, stale_seconds: int) -> bool:
    if not finding.timestamp:
        return False
    try:
        from datetime import datetime, timezone

        text = finding.timestamp.replace("Z", "+00:00")
        moment = datetime.fromisoformat(text)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return (now_epoch - moment.timestamp()) > stale_seconds
    except Exception:  # noqa: BLE001 - an unparseable timestamp is never "stale"
        return False


def _benign_cause(candidates: list[TeamFinding], *, now_epoch: float, stale_seconds: int) -> Optional[ConflictKind]:
    """Name the benign cause of a disagreement, or None if it is genuine.

    Only a difference that is fully EXPLAINED by metadata (a different period,
    unit, currency or basis, an estimate vs a reported figure, or a stale source)
    is classified as benign — never a difference in the number alone.
    """
    periods = {f.period for f in candidates if f.period}
    if len(periods) > 1:
        return ConflictKind.PERIOD_MISMATCH
    units = {f.unit for f in candidates if f.unit}
    if len(units) > 1:
        return ConflictKind.UNIT_MISMATCH
    currencies = {f.currency for f in candidates if f.currency}
    if len(currencies) > 1:
        return ConflictKind.CURRENCY_MISMATCH
    bases = {f.basis for f in candidates if f.basis}
    if len(bases) > 1:
        return ConflictKind.BASIS_MISMATCH
    assumptions = {tuple(sorted(f.assumptions)) for f in candidates}
    if len(assumptions) > 1 and any(assumptions):
        return ConflictKind.ASSUMPTION_MISMATCH
    if any(_is_stale(f, now_epoch=now_epoch, stale_seconds=stale_seconds) for f in candidates):
        return ConflictKind.STALE_DATA
    return None


def detect_conflicts(
    findings: list[TeamFinding],
    *,
    now_epoch: Optional[float] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> list[TeamConflict]:
    """Deterministically detect material disagreements across findings."""
    import time as _time

    now_epoch = _time.time() if now_epoch is None else now_epoch
    by_subject: dict[str, list[TeamFinding]] = {}
    for finding in findings:
        by_subject.setdefault(subject_of(finding), []).append(finding)

    conflicts: list[TeamConflict] = []
    for subject, group in by_subject.items():
        with_values = [f for f in group if _numbers(f)]
        if len(with_values) < 2:
            continue
        distinct: list[float] = []
        for finding in with_values:
            value = _numbers(finding)[0]
            if not any(_values_agree(value, seen) for seen in distinct):
                distinct.append(value)
        if len(distinct) < 2:
            continue

        cause = _benign_cause(with_values, now_epoch=now_epoch, stale_seconds=stale_seconds)
        evidence_refs = sorted({ref for f in with_values for ref in f.evidence_refs})
        if cause is not None:
            conflicts.append(TeamConflict(
                id=new_conflict_id(), subject=subject or "a shared metric", kind=cause,
                status=ConflictStatus.EXPLAINED, material=False,
                finding_ids=[f.id for f in with_values], evidence_refs=evidence_refs,
                resolution_method=f"explained by {cause.value.lower()}; values were not combined",
                detail=f"{len(with_values)} findings differ for the same subject for a benign reason",
            ))
            continue

        sources = sorted({s for f in with_values for s in f.source_refs})
        kind = ConflictKind.CONFLICTING_SOURCES if len(sources) >= 2 else ConflictKind.UNRESOLVED_UNCERTAINTY
        conflicts.append(TeamConflict(
            id=new_conflict_id(), subject=subject or "a shared metric", kind=kind,
            status=ConflictStatus.UNRESOLVED, material=True,
            finding_ids=[f.id for f in with_values], evidence_refs=evidence_refs,
            resolution_method="none — disclosed, not averaged or voted",
            residual_uncertainty="the sources disagree and cannot be reconciled deterministically",
            detail=", ".join(f"{f.agent_id or 'agent'}: {_numbers(f)[0]}" for f in with_values)[:1_000],
        ))
    return conflicts


def _unsupported(
    finding: TeamFinding, *, evidence_exists: Optional[Callable[[str], bool]]
) -> bool:
    if not finding.evidence_refs:
        # No evidence reference at all: the claim is unverifiable, never a fact.
        return True
    if evidence_exists is None:
        return False
    return not any(evidence_exists(ref) for ref in finding.evidence_refs)


def reconcile(
    findings: list[TeamFinding],
    *,
    evidence_exists: Optional[Callable[[str], bool]] = None,
    now_epoch: Optional[float] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> ReconcileResult:
    """Detect conflicts, split supported/unsupported findings, preserve originals."""
    conflicts = detect_conflicts(findings, now_epoch=now_epoch, stale_seconds=stale_seconds)
    unsupported = [f for f in findings if _unsupported(f, evidence_exists=evidence_exists)]
    unsupported_ids = {f.id for f in unsupported}
    supported = [f for f in findings if f.id not in unsupported_ids]
    # A finding with no verifiable evidence is never promoted: flag it as an
    # UNSUPPORTED_CLAIM conflict so it is disclosed in the final result.
    for finding in unsupported:
        conflicts.append(TeamConflict(
            id=new_conflict_id(), subject=subject_of(finding) or finding.claim[:80],
            kind=ConflictKind.UNSUPPORTED_CLAIM, status=ConflictStatus.UNRESOLVED, material=True,
            finding_ids=[finding.id], evidence_refs=list(finding.evidence_refs),
            resolution_method="none — no verifiable evidence reference",
            residual_uncertainty="the claim could not be tied to retrieved evidence",
            detail=finding.claim[:500],
        ))
    return ReconcileResult(conflicts=conflicts, supported=supported, unsupported=unsupported)


async def reconcile_async(
    findings: list[TeamFinding],
    *,
    evidence_exists: Optional[Callable[[str], bool]] = None,
    investigator: Optional[Callable[[TeamConflict, list[TeamFinding]], Any]] = None,
    now_epoch: Optional[float] = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> ReconcileResult:
    """Reconcile, then give a genuine conflict to an investigator to resolve.

    ``investigator`` is an optional async callable returning a mapping with any
    of ``resolved`` (bool), ``method`` (str), ``evidenceRefs`` (list[str]) and
    ``note`` (str). It is the ONLY path by which an unresolved conflict becomes
    RESOLVED, and it can never invent a numeric answer silently: its method and
    evidence are recorded on the conflict.
    """
    result = reconcile(findings, evidence_exists=evidence_exists,
                       now_epoch=now_epoch, stale_seconds=stale_seconds)
    if investigator is None:
        return result
    for conflict in result.conflicts:
        if conflict.status is not ConflictStatus.UNRESOLVED:
            continue
        members = [f for f in findings if f.id in conflict.finding_ids]
        try:
            verdict = await investigator(conflict, members)
        except Exception as exc:  # noqa: BLE001 - an investigator failure is disclosed, not fatal
            conflict.residual_uncertainty = (
                f"investigation failed: {type(exc).__name__}: {exc}"
            )[:500]
            continue
        if not isinstance(verdict, dict):
            continue
        if verdict.get("resolved"):
            conflict.status = ConflictStatus.RESOLVED
            conflict.material = False
            conflict.resolution_method = str(verdict.get("method") or "resolved by investigator")[:500]
            extra = [str(r) for r in (verdict.get("evidenceRefs") or [])]
            conflict.evidence_refs = sorted({*conflict.evidence_refs, *extra})
            conflict.residual_uncertainty = str(verdict.get("note") or "")[:500]
        elif verdict.get("method"):
            conflict.resolution_method = str(verdict["method"])[:500]
    return result


__all__ = [
    "DEFAULT_STALE_SECONDS",
    "ReconcileResult",
    "detect_conflicts",
    "reconcile",
    "reconcile_async",
    "subject_of",
]
