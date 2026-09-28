"""Compaction preservation evaluation (Phase 5).

A labeled set proving the conservative compaction policy does not lose material
information and never merges contradictory or cross-scope records. Seeded into a
fresh temp DB; the real store is never touched.

Run: `python -m harness.eclipse_memory.eval.compaction`
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from ..compaction import detect_proposals, preservation_report
from ..service import EclipseMemoryService
from ..store import EclipseMemoryStore

# Absolute safety floors: a compaction policy is unshippable if it crosses these.
COMPACTION_THRESHOLDS: dict[str, Any] = {
    "crossScopeMerges": 0,
    "contradictoryMerges": 0,
    "lossyAcceptedMerges": 0,
}


@dataclass
class CompactionCase:
    caseId: str
    kind: str  # group | no-group
    memories: list[dict[str, Any]]
    expectGroup: bool
    note: str = ""


@dataclass
class CaseOutcome:
    caseId: str
    kind: str
    groups: int
    accepted: bool = False
    preserved: bool = True
    crossScope: bool = False
    contradictory: bool = False
    error: Optional[str] = None


def _cases() -> list[CompactionCase]:
    return [
        CompactionCase(
            "near-dup-same-scope", "group",
            [
                {"content": "I prefer concise answers in all responses", "subject": "style"},
                {"content": "I prefer concise answers", "subject": "style"},
            ],
            expectGroup=True,
        ),
        CompactionCase(
            "cross-scope-not-merged", "no-group",
            [
                {"content": "I prefer concise answers", "scopeId": "u1"},
                {"content": "I prefer concise answers", "scopeId": "u2"},
            ],
            expectGroup=False, note="scope isolation is authoritative",
        ),
        CompactionCase(
            "contradiction-not-merged", "no-group",
            [
                {"content": "I prefer concise answers", "subject": "style"},
                {"content": "I prefer detailed answers", "subject": "style"},
            ],
            expectGroup=False, note="contradiction must go to review, not compaction",
        ),
        CompactionCase(
            "unrelated-not-merged", "no-group",
            [
                {"content": "I prefer concise answers", "subject": "style"},
                {"content": "My timezone is Asia/Karachi", "subject": "locale"},
            ],
            expectGroup=False,
        ),
        CompactionCase(
            "subset-same-statement", "group",
            [
                {"content": "Use tabs for indentation in this project", "subject": "style"},
                {"content": "Use tabs for indentation", "subject": "style"},
            ],
            expectGroup=True,
        ),
    ]


def run_compaction_eval() -> dict[str, Any]:
    directory = tempfile.mkdtemp(prefix="be-compacteval-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    outcomes: list[CaseOutcome] = []
    try:
        for case in _cases():
            # Seed each case into a FRESH temp store so groups don't bleed.
            sub = tempfile.mkdtemp(prefix="be-compactcase-")
            svc = EclipseMemoryService(EclipseMemoryStore(os.path.join(sub, "eclipse-memory.db")))
            try:
                for memory in case.memories:
                    svc.write_memory(
                        memory_type="preference", content=memory["content"],
                        source="explicit_user", scope="user",
                        scope_id=memory.get("scopeId", "u1"),
                        subject=memory.get("subject"), allow_duplicate=True,
                    )
                memories = svc.store.list_memories(limit=100)
                # Persisted proposals (dicts with ids) so acceptance can be exercised.
                persisted = svc.detect_compaction(persist=True)
                groups = len(persisted)
                proposals = detect_proposals(memories)
                outcome = CaseOutcome(caseId=case.caseId, kind=case.kind, groups=groups)
                if case.expectGroup and not proposals:
                    outcome.error = "expected a proposal but none was produced"
                if not case.expectGroup and proposals:
                    # A wrong group: classify whether it crossed scope or merged a
                    # contradiction (the safety floor).
                    for proposal in proposals:
                        members = [svc.store.get_memory(mid) for mid in proposal.members]
                        scopes = {(m.get("scope"), m.get("scopeId")) for m in members if m}
                        if len(scopes) > 1:
                            outcome.crossScope = True
                    from ..compaction import _looks_contradictory  # noqa: PLC0415

                    for proposal in proposals:
                        ids = proposal.members
                        for x in range(len(ids)):
                            for y in range(x + 1, len(ids)):
                                a = svc.store.get_memory(ids[x]); b = svc.store.get_memory(ids[y])
                                if a and b and _looks_contradictory(a, b):
                                    outcome.contradictory = True
                if persisted:
                    first = persisted[0]
                    report = preservation_report(
                        [svc.store.get_memory(mid) for mid in first["memberIds"]],
                        first["mergedContent"],
                    )
                    outcome.preserved = report["preserved"]
                    # Accept and verify the actual merge preserves everything.
                    accepted = svc.accept_compaction(first["id"])
                    if accepted.get("ok"):
                        outcome.accepted = True
                        outcome.preserved = bool(accepted["preservation"]["preserved"])
                outcomes.append(outcome)
            finally:
                svc.close()
    finally:
        service.close()

    metrics = {
        "crossScopeMerges": sum(1 for o in outcomes if o.crossScope),
        "contradictoryMerges": sum(1 for o in outcomes if o.contradictory),
        "lossyAcceptedMerges": sum(1 for o in outcomes if o.accepted and not o.preserved),
        "cases": len(outcomes),
        "groupRecall": _rate([o for o in outcomes if o.kind == "group"], lambda o: o.groups > 0),
        "noGroupPrecision": _rate([o for o in outcomes if o.kind == "no-group"], lambda o: o.groups == 0),
    }
    return {
        "datasetName": "compaction-preservation",
        "version": 1,
        "cases": [
            {"caseId": o.caseId, "kind": o.kind, "groups": o.groups, "accepted": o.accepted,
             "preserved": o.preserved, "crossScope": o.crossScope,
             "contradictory": o.contradictory, "error": o.error}
            for o in outcomes
        ],
        "metrics": metrics,
    }


def _rate(items: list[CaseOutcome], predicate: Any) -> float:
    if not items:
        return 1.0
    return round(sum(1 for item in items if predicate(item)) / len(items), 3)


def check_compaction_thresholds(report: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    metrics = report["metrics"]
    for key, limit in COMPACTION_THRESHOLDS.items():
        if metrics.get(key, 0) > limit:
            failures.append(f"{key}: expected <= {limit}, got {metrics.get(key)}")
    return {"passed": not failures, "failures": failures}


def format_compaction_report(report: dict[str, Any]) -> str:
    lines = [f"Compaction preservation eval — {report['datasetName']} v{report['version']}", ""]
    for case in report["cases"]:
        flag = " GROUP" if case["groups"] else ""
        lines.append(f"  [{case['kind']:>8}] {case['caseId']:<28} groups={case['groups']}{flag}"
                     + (f" ERROR={case['error']}" if case["error"] else ""))
    m = report["metrics"]
    lines.append(
        f"  crossScope={m['crossScopeMerges']} contradictory={m['contradictoryMerges']} "
        f"lossy={m['lossyAcceptedMerges']} groupRecall={m['groupRecall']} noGroupPrecision={m['noGroupPrecision']}"
    )
    return "\n".join(lines)


__all__ = [
    "COMPACTION_THRESHOLDS",
    "check_compaction_thresholds",
    "format_compaction_report",
    "run_compaction_eval",
]
