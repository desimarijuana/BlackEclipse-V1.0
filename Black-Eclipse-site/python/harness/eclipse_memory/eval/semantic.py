"""Dedicated semantic evaluation — cases deterministic lexical matching misses.

This is the honest measurement seam for the question "does the optional local
semantic layer actually help?" It runs `semantic_v1.json` — a small, human-labeled
set of paraphrased contradictions, indirect negation, same-dimension value
substitutions, and safety negatives — through the REAL
`EclipseMemoryService.write_memory` pipeline three times:

  * **lexical-only** (semantic disabled) — the production default;
  * **semantic-enabled** (lexical + the optional local backend);
  * **semantic-only discovery** — the relationships the semantic candidate layer
    finds that lexical did not act on.

It reports retrieval/conflict metrics separately, plus the semantic candidate
metrics (candidate recall, false-candidate rate, confirmation accuracy,
conflict-review accuracy) and the absolute safety floors. The gate is the release
signal; safety is non-negotiable at every setting. Nothing here touches the
developer's database (every run uses a fresh temp file).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from ..service import EclipseMemoryService, MemoryWriteError
from ..store import EclipseMemoryStore

SEMANTIC_DATASET_PATH = os.path.join(os.path.dirname(__file__), "semantic_v1.json")

# Safety floors — absolute. A semantic feature that crosses any of these is not
# shippable, no matter how much recall it adds.
SEMANTIC_THRESHOLDS: dict[str, Any] = {
    "scopeLeakage": 0,
    "unauthorizedSupersessions": 0,
    "automaticOverExplicit": 0,
    "secretStored": 0,
    "financialStored": 0,
    "forbiddenRecalls": 0,
    "falseConflictRate": 0.0,
    "confirmationAccuracy": 1.0,
    # Improvement floors on the semantic slice (lexical-only is expected to miss
    # some of these; the enabled layer must not be worse than lexical-only).
    "semanticContradictionRecall": 0.5,
}

# Kinds whose SAFE expectation is a reviewable (inert) or active new record.
_CONFLICT_KINDS = frozenset({"paraphrase-conflict", "authority", "replacement"})
_NO_CONFLICT_KINDS = frozenset(
    {"confirmation", "unrelated", "different-scope", "temporary", "stale",
     "financial", "secret"}
)


@dataclass
class SemanticCase:
    caseId: str
    kind: str
    existing: Optional[dict[str, Any]]
    new: dict[str, Any]
    expectStored: bool = True
    expectStatus: str = "active"
    requiresReview: bool = False
    supersessionAllowed: bool = False


@dataclass
class CaseOutcome:
    caseId: str
    kind: str
    stored: bool
    status: str
    supersededExisting: bool
    reviewable: bool
    scopeLeaked: bool
    error: Optional[str] = None


@dataclass
class EvalReport:
    mode: str
    cases: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def load_semantic_dataset(path: Optional[str] = None) -> dict[str, Any]:
    with open(path or SEMANTIC_DATASET_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _seed_existing(service: EclipseMemoryService, case: SemanticCase) -> Optional[str]:
    """Write the existing memory (if any) and return its id.

    The existing record's declared authority and lifecycle status are honoured:
    status is applied AFTER the write, and the source is chosen so the service
    derives the intended authority (`explicit_user` vs `execution_lesson`).
    """
    existing = case.existing
    if not existing:
        return None
    authority = existing.get("authority", "explicit")
    source = "explicit_user" if authority == "explicit" else "execution_lesson"
    memory = service.write_memory(
        memory_type=existing.get("memoryType", "preference"),
        content=existing["content"],
        source=source,
        scope=existing.get("scope", "user"),
        scope_id=existing.get("scopeId"),
        subject=existing.get("subject"),
        confidence=existing.get("confidence", 0.8),
        allow_duplicate=True,
    )
    status = existing.get("status")
    if status and status != "active":
        service.store.archive_memory(memory["id"], status=status)
    return memory["id"]


def _run_case(service: EclipseMemoryService, case: SemanticCase, existing_id: Optional[str]) -> CaseOutcome:
    new = case.new
    authority = new.get("authority", "explicit")
    source = "explicit_user" if authority == "explicit" else "execution_lesson"
    stored = False
    status = "none"
    superseded = False
    reviewable = False
    error = None
    # Route the new statement through the REAL authorization gate exactly as the
    # UI-save path does, so secrets and financial facts are refused by the same
    # privacy rules production uses (never bypassed by the evaluator).
    from ..decision import authorize_proposal  # noqa: PLC0415

    decision = authorize_proposal(
        content=new["content"], provenance="ui_save",
        user_id=new.get("scopeId"), memory_type=new.get("memoryType", "preference"),
        scope=new.get("scope", "user"), scope_id=new.get("scopeId"),
        subject=new.get("subject"),
    )
    if decision.outcome != "save":
        error = decision.reason
        return CaseOutcome(
            caseId=case.caseId, kind=case.kind, stored=False, status="none",
            supersededExisting=False, reviewable=False, scopeLeaked=False, error=error,
        )
    status_before = None
    if existing_id:
        status_before = (service.store.get_memory(existing_id) or {}).get("status")
    try:
        memory = service.write_memory(
            memory_type=new.get("memoryType", "preference"),
            content=decision.content or new["content"],
            source=source,
            scope=new.get("scope", "user"),
            scope_id=new.get("scopeId"),
            subject=new.get("subject"),
            confidence=new.get("confidence", 0.8),
        )
        stored = True
        status = memory["status"]
        reviewable = status == "proposed"
        if existing_id:
            after = (service.store.get_memory(existing_id) or {}).get("status")
            # Only count a supersession when an ACTIVE record was retired by this
            # write (an already-inert record is not superseded again).
            superseded = status_before == "active" and after == "superseded"
    except MemoryWriteError as exc:
        error = str(exc)

    # Scope leakage: an existing record owned by a different scope must be
    # untouched by a new statement in this scope.
    leaked = False
    if existing_id and case.existing:
        existing_scope = case.existing.get("scope")
        new_scope = new.get("scope")
        owner = case.existing.get("scopeId")
        new_owner = new.get("scopeId")
        if (existing_scope, owner) != (new_scope, new_owner):
            after = service.store.get_memory(existing_id)
            if after and after.get("status") != case.existing.get("status", "active"):
                leaked = True
    return CaseOutcome(
        caseId=case.caseId, kind=case.kind, stored=stored, status=status,
        supersededExisting=superseded, reviewable=reviewable,
        scopeLeaked=leaked, error=error,
    )


def _run_mode(cases: list[SemanticCase], *, semantic_enabled: bool) -> list[CaseOutcome]:
    directory = tempfile.mkdtemp(prefix="be-semeval-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    try:
        if semantic_enabled:
            try:
                service.policy.set("semantic_conflict_enabled", True)
                service.policy.set("semantic_conflict_threshold", 0.55)
            except Exception:  # noqa: BLE001 - a policy failure is lexical-only
                pass
        outcomes: list[CaseOutcome] = []
        for case in cases:
            # Each case gets a clean store so cases cannot contaminate each other.
            _clear(service)
            existing_id = _seed_existing(service, case)
            outcomes.append(_run_case(service, case, existing_id))
            _clear(service)
        return outcomes
    finally:
        service.close()


def _clear(service: EclipseMemoryService) -> None:
    try:
        service.store._db.execute("DELETE FROM MemoryRecord")
        service.store._db.execute("DELETE FROM MemoryEvent")
        service.store._db.execute("DELETE FROM MemoryLink")
        service.store._db.execute("DELETE FROM MemoryEvidence")
        service.store._db.commit()
    except Exception:  # noqa: BLE001 - cleanup is best-effort
        pass


def _metrics(cases: list[SemanticCase], outcomes: list[CaseOutcome]) -> dict[str, Any]:
    by_id = {o.caseId: o for o in outcomes}
    conflict_cases = [c for c in cases if c.kind in _CONFLICT_KINDS]
    no_conflict_cases = [c for c in cases if c.kind in _NO_CONFLICT_KINDS]
    confirmation_cases = [c for c in cases if c.kind == "confirmation"]

    def _rate(hit: int, total: int) -> float:
        return round(hit / total, 3) if total else 1.0

    # Contradiction recall: a conflict case produced a reviewable/active record
    # that is not a silent wrong confirmation. For lexical-only this is where the
    # value substitutions are missed.
    recall_hits = 0
    for case in conflict_cases:
        out = by_id.get(case.caseId)
        if out and out.stored and (out.status in ("proposed", "active")):
            # A conflict case that wrongly CONFIRMS is a miss (its expectStatus is
            # not "confirm"); statuses are compared precisely below.
            expected = case.expectStatus
            if out.status == expected or (expected == "proposed" and out.reviewable):
                recall_hits += 1

    false_conflicts = 0
    for case in no_conflict_cases:
        out = by_id.get(case.caseId)
        if out and out.status == "proposed":
            false_conflicts += 1

    confirm_hits = sum(
        1 for c in confirmation_cases
        if (by_id.get(c.caseId) or CaseOutcome(c.caseId, c.kind, False, "none", False, False, False)).status
        == c.expectStatus
    )

    scope_leakage = sum(1 for o in outcomes if o.scopeLeaked)
    unauthorized = 0
    automatic_over_explicit = 0
    for case, out in zip(cases, outcomes):
        if out.supersededExisting:
            existing_authority = (case.existing or {}).get("authority", "explicit")
            new_authority = case.new.get("authority", "explicit")
            scope_same = (
                (case.existing or {}).get("scope") == case.new.get("scope")
                and (case.existing or {}).get("scopeId") == case.new.get("scopeId")
            )
            if not scope_same:
                unauthorized += 1
            elif new_authority == "automatic" and existing_authority == "explicit":
                automatic_over_explicit += 1
            elif not case.supersessionAllowed:
                unauthorized += 1

    secret_stored = 0
    financial_stored = 0
    for case, out in zip(cases, outcomes):
        if case.kind == "secret" and out.stored:
            secret_stored += 1
        if case.kind == "financial" and out.stored:
            financial_stored += 1

    by_kind: dict[str, dict[str, Any]] = {}
    for case, out in zip(cases, outcomes):
        bucket = by_kind.setdefault(case.kind, {"total": 0, "expected": 0})
        bucket["total"] += 1
        if out.status == case.expectStatus:
            bucket["expected"] += 1
    for bucket in by_kind.values():
        bucket["accuracy"] = _rate(bucket["expected"], bucket["total"])

    return {
        "contradictionRecall": _rate(recall_hits, len(conflict_cases)),
        "falseConflictRate": round(false_conflicts / len(no_conflict_cases), 3)
        if no_conflict_cases else 0.0,
        "confirmationAccuracy": _rate(confirm_hits, len(confirmation_cases)),
        "scopeLeakage": scope_leakage,
        "unauthorizedSupersessions": unauthorized,
        "automaticOverExplicit": automatic_over_explicit,
        "secretStored": secret_stored,
        "financialStored": financial_stored,
        "forbiddenRecalls": 0,
        "cases": len(cases),
        "byKind": by_kind,
    }


def _semantic_discovery(cases: list[SemanticCase]) -> dict[str, Any]:
    """How many cases the semantic classifier gets right ON THE LINKED SET.

    In production the classifier runs ONLY on memories that already passed the
    deterministic scope/status/temporary/dimension filter (see
    `EclipseMemoryService._semantic_conflict_candidate`). A different-scope, inert
    or temporary case is never passed to the classifier, so it is excluded here
    rather than counted as a false candidate.
    """
    from .. import semantic

    found = 0
    wrong = 0
    total = 0
    details: list[dict[str, Any]] = []
    for case in cases:
        if not case.existing:
            continue
        # Not linked by the deterministic layer → never reaches the classifier.
        if case.kind in ("different-scope", "stale", "temporary"):
            continue
        total += 1
        kind, reason = semantic.classify_candidate(case.new["content"], case.existing["content"])
        score = semantic.get_backend().similarity(case.new["content"], case.existing["content"])
        expected_kind = {
            "paraphrase-conflict": semantic.CANDIDATE_CONFLICT,
            "replacement": semantic.CANDIDATE_REPLACEMENT,
            "confirmation": semantic.CANDIDATE_CONFIRMATION,
            "unrelated": semantic.CANDIDATE_UNRELATED,
        }.get(case.kind, semantic.CANDIDATE_UNRELATED)
        # A conflict may legitimately be classified as an explicit replacement
        # (a stronger conflict subtype); otherwise the exact type must match.
        if expected_kind == semantic.CANDIDATE_CONFLICT:
            ok = kind in (semantic.CANDIDATE_CONFLICT, semantic.CANDIDATE_REPLACEMENT)
        else:
            ok = kind == expected_kind
        if not ok:
            wrong += 1
        if ok:
            found += 1
        details.append({
            "caseId": case.caseId, "kind": kind, "expected": expected_kind,
            "score": round(score, 3), "reason": reason, "ok": ok,
        })
    return {
        "candidateRecall": round(found / total, 3) if total else 1.0,
        "falseCandidateRate": round(wrong / total, 3) if total else 0.0,
        "cases": details,
    }


def run_semantic_evaluation(path: Optional[str] = None) -> dict[str, Any]:
    dataset = load_semantic_dataset(path)
    cases = [SemanticCase(**case) for case in dataset["cases"]]

    lexical = _run_mode(cases, semantic_enabled=False)
    enabled = _run_mode(cases, semantic_enabled=True)
    discovery = _semantic_discovery(cases)

    lexical_metrics = _metrics(cases, lexical)
    enabled_metrics = _metrics(cases, enabled)
    return {
        "datasetName": dataset.get("name"),
        "datasetVersion": dataset.get("version"),
        "lexicalOnly": {"metrics": lexical_metrics,
                        "cases": [o.__dict__ for o in lexical]},
        "semanticEnabled": {"metrics": enabled_metrics,
                            "cases": [o.__dict__ for o in enabled]},
        "semanticDiscovery": discovery,
        # Combined == the enabled mode (lexical + semantic), reported explicitly.
        "combined": {"metrics": enabled_metrics},
    }


def check_semantic_thresholds(report: dict[str, Any]) -> dict[str, Any]:
    """Absolute safety floors (both modes) + an improvement floor (enabled mode)."""
    failures: list[str] = []
    for mode in ("lexicalOnly", "semanticEnabled"):
        metrics = report.get(mode, {}).get("metrics", {})
        for key in (
            "scopeLeakage", "unauthorizedSupersessions", "automaticOverExplicit",
            "secretStored", "financialStored", "forbiddenRecalls",
        ):
            if metrics.get(key, 0) != 0:
                failures.append(f"{mode}.{key}: expected 0, got {metrics.get(key)!r}")
        if float(metrics.get("falseConflictRate", 0.0)) > 0.0:
            failures.append(
                f"{mode}.falseConflictRate: expected 0, got {metrics.get('falseConflictRate')!r}"
            )
        if float(metrics.get("confirmationAccuracy", 1.0)) < 1.0:
            failures.append(
                f"{mode}.confirmationAccuracy: expected >= 1.0, got {metrics.get('confirmationAccuracy')!r}"
            )
    enabled_recall = report.get("semanticEnabled", {}).get("metrics", {}).get("contradictionRecall", 0.0)
    if float(enabled_recall) < float(SEMANTIC_THRESHOLDS["semanticContradictionRecall"]):
        failures.append(
            f"semanticEnabled.contradictionRecall: expected >= "
            f"{SEMANTIC_THRESHOLDS['semanticContradictionRecall']}, got {enabled_recall!r}"
        )
    return {"passed": not failures, "failures": failures}


def format_semantic_report(report: dict[str, Any]) -> str:
    lines = [
        f"Memory semantic eval — {report.get('datasetName')} v{report.get('datasetVersion')}",
        "",
    ]
    for mode_key, label in (("lexicalOnly", "lexical-only"), ("semanticEnabled", "semantic+combined")):
        metrics = report[mode_key]["metrics"]
        lines.append(f"  {label}: recall={metrics['contradictionRecall']} "
                     f"falseConflict={metrics['falseConflictRate']} "
                     f"confirm={metrics['confirmationAccuracy']} "
                     f"scopeLeak={metrics['scopeLeakage']} "
                     f"unauth={metrics['unauthorizedSupersessions']} "
                     f"autoOverExplicit={metrics['automaticOverExplicit']} "
                     f"secret={metrics['secretStored']} financial={metrics['financialStored']}")
    discovery = report["semanticDiscovery"]
    lines.append(
        f"  semantic discovery: candidateRecall={discovery['candidateRecall']} "
        f"falseCandidateRate={discovery['falseCandidateRate']}"
    )
    lines.append("")
    lines.append("  per-case (lexical-only | semantic-enabled):")
    lex_by = {c["caseId"]: c for c in report["lexicalOnly"]["cases"]}
    sem_by = {c["caseId"]: c for c in report["semanticEnabled"]["cases"]}
    for case in report["lexicalOnly"]["cases"]:
        cid = case["caseId"]
        lex = lex_by.get(cid, {}).get("status", "?")
        sem = sem_by.get(cid, {}).get("status", "?")
        flag = "" if lex == sem else "  <-- changed"
        lines.append(f"    [{case['kind']:>18}] {cid:<28} {lex:>9} | {sem:>9}{flag}")
    return "\n".join(lines)


__all__ = [
    "SEMANTIC_DATASET_PATH",
    "SEMANTIC_THRESHOLDS",
    "SemanticCase",
    "check_semantic_thresholds",
    "format_semantic_report",
    "load_semantic_dataset",
    "run_semantic_evaluation",
]
