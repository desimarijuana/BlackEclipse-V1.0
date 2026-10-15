"""Evidence-based conflict reconciliation (Feature D)."""

from __future__ import annotations

import asyncio

from harness.team.conflicts import detect_conflicts, reconcile, reconcile_async, subject_of
from harness.team.model import ConflictKind, ConflictStatus, TeamFinding


def _f(fid, claim, **kw):
    return TeamFinding(id=fid, claim=claim, **kw)


def test_no_conflict_for_unrelated_subjects():
    findings = [
        _f("1", "Tesla revenue is 96", evidence_refs=["e1"]),
        _f("2", "Nvidia margins are 55", evidence_refs=["e2"]),
    ]
    assert detect_conflicts(findings, now_epoch=1_000_000) == []


def test_same_value_is_not_a_conflict():
    findings = [
        _f("1", "Tesla revenue is 96.8", evidence_refs=["e1"]),
        _f("2", "Tesla revenue is 96.8", evidence_refs=["e2"]),
    ]
    assert detect_conflicts(findings, now_epoch=1_000_000) == []


def test_genuine_disagreement_is_unresolved_and_not_averaged():
    findings = [
        _f("1", "Tesla revenue is 96", agent_id="research-agent", source_refs=["sec"]),
        _f("2", "Tesla revenue is 88", agent_id="news-agent", source_refs=["blog"]),
    ]
    conflicts = detect_conflicts(findings, now_epoch=1_000_000)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict.status is ConflictStatus.UNRESOLVED
    assert conflict.material is True
    assert conflict.kind is ConflictKind.CONFLICTING_SOURCES
    # The original values are preserved verbatim; nothing is averaged.
    assert set(conflict.finding_ids) == {"1", "2"}
    assert "92" not in (conflict.detail or "")


def test_different_period_explains_the_difference():
    findings = [
        _f("1", "Tesla revenue is 96", period="FY2024", evidence_refs=["e1"]),
        _f("2", "Tesla revenue is 88", period="FY2023", evidence_refs=["e2"]),
    ]
    conflicts = detect_conflicts(findings, now_epoch=1_000_000)
    assert len(conflicts) == 1
    assert conflicts[0].kind is ConflictKind.PERIOD_MISMATCH
    assert conflicts[0].status is ConflictStatus.EXPLAINED
    assert conflicts[0].material is False


def test_different_currency_and_basis_are_explained():
    currency = detect_conflicts([
        _f("1", "Revenue is 100", currency="USD", evidence_refs=["e1"]),
        _f("2", "Revenue is 92", currency="EUR", evidence_refs=["e2"]),
    ], now_epoch=1_000_000)[0]
    assert currency.kind is ConflictKind.CURRENCY_MISMATCH
    basis = detect_conflicts([
        _f("1", "EPS is 3.2", basis="GAAP", evidence_refs=["e1"]),
        _f("2", "EPS is 3.9", basis="non-GAAP", evidence_refs=["e2"]),
    ], now_epoch=1_000_000)[0]
    assert basis.kind is ConflictKind.BASIS_MISMATCH


def test_claims_without_evidence_are_unsupported():
    findings = [
        _f("1", "Tesla revenue is 96", evidence_refs=["missing"]),
        _f("2", "Tesla is undervalued"),
    ]
    result = reconcile(findings, evidence_exists=lambda ref: ref == "present", now_epoch=1_000_000)
    assert {f.id for f in result.unsupported} == {"1", "2"}
    assert any(c.kind is ConflictKind.UNSUPPORTED_CLAIM for c in result.conflicts)


def test_investigator_can_resolve_a_genuine_conflict():
    findings = [
        _f("1", "Tesla revenue is 96", agent_id="research-agent", source_refs=["sec"]),
        _f("2", "Tesla revenue is 88", agent_id="news-agent", source_refs=["blog"]),
    ]

    async def investigator(conflict, members):
        return {"resolved": True, "method": "found the authoritative filing",
                "evidenceRefs": ["ev_x"], "note": "the blog misquoted the year"}

    result = asyncio.run(reconcile_async(findings, investigator=investigator, now_epoch=1_000_000))
    resolved = [c for c in result.conflicts if c.status is ConflictStatus.RESOLVED]
    assert resolved and "ev_x" in resolved[0].evidence_refs


def test_subject_key_is_stable_across_wording():
    a = _f("1", "Tesla revenue was 96 billion")
    b = _f("2", "Tesla revenue 96 billion")
    assert subject_of(a) == subject_of(b)
