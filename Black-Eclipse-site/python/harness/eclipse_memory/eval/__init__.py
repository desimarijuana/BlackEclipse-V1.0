"""Eclipse-Memory retrieval evaluation — a small, versioned, labeled set.

This is the measurement seam for memory retrieval. It is deliberately separate
from the retrieval implementation so a change to ranking/filtering can be judged
against recorded results (including negative cases: irrelevant near-matches,
stale/superseded facts, scope boundaries and no-match queries) rather than a
feeling that recall "looks better".

Design:
  * `dataset_v1.json` is a human-labeled set of prompts with their expected
    memories and the acting scope.
  * `run_evaluation()` seeds a fresh temporary `eclipse-memory.db` from the
    dataset's fixed memory corpus, runs the REAL `EclipseMemoryService.retrieve`
    for each case, and reports precision, recall, scope leakage and
    context-budget behaviour.
  * Filters remain authoritative and deterministic: semantic similarity is not
    used, and scope/status/privacy filtering decides eligibility before ranking.

Nothing here is part of production retrieval — it imports it. It never touches
the developer's real memory database (every run uses a temp file).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Optional

from ..service import EclipseMemoryService
from ..store import EclipseMemoryStore
from .. import retrieval as _retrieval

_STANDING_TYPES = _retrieval._STANDING_TYPES

DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset_v1.json")

# Release thresholds. A retrieval change is a REGRESSION if it crosses these.
# Safety is absolute (forbidden hits and scope leakage must be zero) and the
# lexical slice the retriever is designed to serve must stay complete. Recall and
# precision are floors, not targets: an improvement is always allowed.
THRESHOLDS: dict[str, Any] = {
    "forbiddenHits": 0,
    "scopeLeakage": 0,
    "noMatchClean": True,
    "overBudgetCases": 0,
    "recallSupported": 1.0,
    "recall": 0.9,
    "precision": 0.66,
}


def check_thresholds(report: dict[str, Any]) -> dict[str, Any]:
    """Compare a report's metrics against the release thresholds.

    Returns `{"passed": bool, "failures": [...]}`. A change that introduces a
    forbidden hit, a scope leak, or excessive no-match recall fails here — the
    eval is the evidence, and these are the gates.
    """
    metrics = report.get("metrics", {})
    failures: list[str] = []
    for key, limit in THRESHOLDS.items():
        value = metrics.get(key)
        if value is None:
            continue
        if limit is True:
            if value is not True:
                failures.append(f"{key}: expected True, got {value!r}")
        elif limit == 0:
            if value != 0:
                failures.append(f"{key}: expected 0, got {value!r}")
        else:
            if float(value) < float(limit):
                failures.append(f"{key}: expected >= {limit}, got {value!r}")
    return {"passed": not failures, "failures": failures}


@dataclass
class EvalCase:
    caseId: str
    query: str
    actorScope: Optional[str] = None
    scopeId: Optional[str] = None
    expectKeys: list[str] = field(default_factory=list)
    forbidKeys: list[str] = field(default_factory=list)
    forbidContent: list[str] = field(default_factory=list)
    kind: str = "normal"


@dataclass
class CaseResult:
    caseId: str
    kind: str
    selectedIds: list[str]
    expectedIds: list[str]
    hitIds: list[str]
    missedIds: list[str]
    forbiddenHits: list[str]
    scopeLeaks: list[str]
    usedChars: int
    budgetChars: int
    selected: int
    selectedTopical: int = 0
    topicalHits: int = 0
    durationMs: float = 0.0

    @property
    def precision(self) -> float:
        # Topical precision: only topical selections count in the denominator,
        # because standing user rules (preference/constraint) are intentional
        # per-turn personalization by design. A case that selected no topical
        # memory has no denominator; its safety is captured by forbiddenHits and
        # scopeLeaks, so precision is reported as 1.0 rather than misleading 0.0.
        if not self.selectedTopical:
            return 1.0
        return self.topicalHits / self.selectedTopical

    @property
    def recall(self) -> float:
        if not self.expectedIds:
            return 1.0
        return len(self.hitIds) / len(self.expectedIds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "caseId": self.caseId, "kind": self.kind,
            "selectedIds": self.selectedIds, "expectedIds": self.expectedIds,
            "hitIds": self.hitIds, "missedIds": self.missedIds,
            "forbiddenHits": self.forbiddenHits, "scopeLeaks": self.scopeLeaks,
            "precision": round(self.precision, 3), "recall": round(self.recall, 3),
            "usedChars": self.usedChars, "budgetChars": self.budgetChars,
            "selected": self.selected, "selectedTopical": self.selectedTopical,
            "durationMs": round(self.durationMs, 3),
        }


def load_dataset(path: Optional[str] = None) -> dict[str, Any]:
    with open(path or DATASET_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _seed(service: EclipseMemoryService, corpus: list[dict[str, Any]]) -> dict[str, str]:
    """Write the corpus and return a `key -> generated id` map.

    Corpus entries carry a stable `key` (not a database id) so the dataset is
    readable and portable. A `status` other than `active` is applied AFTER the
    write so a case can prove an inert memory is never recalled.
    """
    key_to_id: dict[str, str] = {}
    for entry in corpus:
        memory = service.write_memory(
            memory_type=entry["memoryType"],
            content=entry["content"],
            source=entry.get("source", "manual"),
            scope=entry.get("scope", "general"),
            scope_id=entry.get("scopeId"),
            subject=entry.get("subject"),
            confidence=entry.get("confidence", 0.6),
            importance=entry.get("importance", 0.5),
            verification=entry.get("verification", "unverified"),
            allow_duplicate=True,
        )
        key_to_id[entry["key"]] = memory["id"]
    for entry in corpus:
        if entry.get("status") and entry["status"] != "active":
            service.store.archive_memory(key_to_id[entry["key"]], status=entry["status"])
    return key_to_id


def run_evaluation(path: Optional[str] = None) -> dict[str, Any]:
    """Run the labeled set against the real retrieval path. Returns a report."""
    dataset = load_dataset(path)
    corpus = dataset["memories"]
    cases = [EvalCase(**case) for case in dataset["cases"]]

    directory = tempfile.mkdtemp(prefix="be-memeval-")
    service = EclipseMemoryService(EclipseMemoryStore(os.path.join(directory, "eclipse-memory.db")))
    results: list[CaseResult] = []
    try:
        key_to_id = _seed(service, corpus)
        corpus_by_key = {key_to_id[e["key"]]: e for e in corpus}
        for case in cases:
            outcome = service.retrieve(
                query=case.query, actor_scope=case.actorScope,
                scope_id=case.scopeId, limit=8,
            )
            selected = outcome.memories
            selected_ids = [m["id"] for m in selected]
            selected_content = " ".join(m["content"] for m in selected).lower()
            expect_ids = [key_to_id[k] for k in case.expectKeys if k in key_to_id]
            forbid_ids = [key_to_id[k] for k in case.forbidKeys if k in key_to_id]
            hit = [i for i in expect_ids if i in selected_ids]
            missed = [i for i in expect_ids if i not in selected_ids]
            forbidden = [i for i in forbid_ids if i in selected_ids]
            forbidden += [c for c in case.forbidContent if c.lower() in selected_content]
            # Precision is computed over TOPICAL recall only: standing user rules
            # (preference/constraint) are intentional per-turn personalization and
            # are reported separately (`totalStanding`). `topicalHit` counts only
            # expected memories that are themselves topical.
            selected_topical = [m["id"] for m in selected if m["memoryType"] not in _STANDING_TYPES]
            topical_expect = [
                i for i in expect_ids
                if (corpus_by_key.get(i) or {}).get("memoryType") not in _STANDING_TYPES
            ]
            topical_hit = [i for i in topical_expect if i in selected_topical]
            # Scope leak: a user-scoped memory belonging to another user.
            leaks = [
                m["id"] for m in selected
                if m.get("scope") == "user" and m.get("scopeId") and m.get("scopeId") != case.scopeId
            ]
            diagnostics = outcome.diagnostics
            results.append(CaseResult(
                caseId=case.caseId, kind=case.kind, selectedIds=selected_ids,
                expectedIds=expect_ids, hitIds=hit, missedIds=missed,
                forbiddenHits=forbidden, scopeLeaks=leaks,
                usedChars=int(diagnostics.get("usedChars", 0)),
                budgetChars=int(diagnostics.get("budgetChars", 0)),
                selected=len(selected), selectedTopical=len(selected_topical),
                topicalHits=len(topical_hit),
                durationMs=float(diagnostics.get("durationMs", 0) or 0),
            ))
    finally:
        service.close()

    positive = [r for r in results if r.expectedIds]
    no_match = [r for r in results if r.kind == "no-match"]
    total_expected = sum(len(r.expectedIds) for r in positive)
    total_hit = sum(len(r.hitIds) for r in positive)
    total_selected_topical = sum(r.selectedTopical for r in results)
    total_topical_hits = sum(r.topicalHits for r in results)
    total_forbidden = sum(len(r.forbiddenHits) for r in results)
    total_leaks = sum(len(r.scopeLeaks) for r in results)

    # Per-kind recall, so a lexical-only retriever's known gap (a synonym
    # paraphrase sharing no term) is MEASURED and visible separately from the
    # exact/paraphrase slice it does support. Semantic retrieval is deliberately
    # not added; this records the limitation instead of hiding it.
    by_kind: dict[str, dict[str, Any]] = {}
    for result in results:
        if not result.expectedIds:
            continue
        bucket = by_kind.setdefault(result.kind, {"expected": 0, "hit": 0})
        bucket["expected"] += len(result.expectedIds)
        bucket["hit"] += len(result.hitIds)
    for bucket in by_kind.values():
        bucket["recall"] = round(bucket["hit"] / bucket["expected"], 3) if bucket["expected"] else 1.0

    supported = [r for r in positive if r.kind in ("normal", "paraphrase")]
    supported_expected = sum(len(r.expectedIds) for r in supported)
    supported_hit = sum(len(r.hitIds) for r in supported)

    return {
        "datasetName": dataset.get("name"),
        "datasetVersion": dataset.get("version"),
        "cases": [r.to_dict() for r in results],
        "metrics": {
            "recall": round(total_hit / total_expected, 3) if total_expected else 1.0,
            "precision": round(total_topical_hits / total_selected_topical, 3) if total_selected_topical else 1.0,
            "scopeLeakage": total_leaks,
            "forbiddenHits": total_forbidden,
            "noMatchClean": all(r.selectedTopical == 0 for r in no_match),
            "overBudgetCases": sum(1 for r in results if r.usedChars > r.budgetChars),
            "totalSelected": sum(len(r.selectedIds) for r in results),
            "totalStanding": sum(r.selected - r.selectedTopical for r in results),
            # The lexical slice the retriever is designed to serve.
            "recallSupported": round(supported_hit / supported_expected, 3) if supported_expected else 1.0,
            "byKind": by_kind,
            # Latency (deterministic path only — no network/model). Reported so a
            # future semantic layer can be compared against the lexical baseline.
            "latencyMs": {
                "mean": round(sum(r.durationMs for r in results) / len(results), 3) if results else 0.0,
                "max": round(max((r.durationMs for r in results), default=0.0), 3),
            },
        },
        "budget": {
            "defaultBudgetChars": 4000,
            "maxUsedChars": max((r.usedChars for r in results), default=0),
        },
    }

def format_report(report: dict[str, Any]) -> str:
    lines = [
        f"Memory retrieval eval — {report.get('datasetName')} v{report.get('datasetVersion')}",
        "",
    ]
    for case in report["cases"]:
        flag = ""
        if case["missedIds"]:
            flag += f" MISS={case['missedIds']}"
        if case["forbiddenHits"]:
            flag += f" FORBIDDEN={case['forbiddenHits']}"
        if case["scopeLeaks"]:
            flag += f" LEAK={case['scopeLeaks']}"
        lines.append(
            f"  [{case['kind']:>12}] {case['caseId']:<28} "
            f"P={case['precision']:.2f} R={case['recall']:.2f}{flag}"
        )
    metrics = report["metrics"]
    lines += [
        "",
        f"  recall={metrics['recall']} precision={metrics['precision']} "
        f"scopeLeakage={metrics['scopeLeakage']} forbiddenHits={metrics['forbiddenHits']} "
        f"noMatchClean={metrics['noMatchClean']}",
        f"  recallSupported={metrics.get('recallSupported')} (lexical slice: normal+paraphrase)",
    ]
    by_kind = metrics.get("byKind") or {}
    if by_kind:
        lines.append("  by kind: " + ", ".join(
            f"{kind}={row['recall']} ({row['hit']}/{row['expected']})"
            for kind, row in sorted(by_kind.items())
        ))
    return "\n".join(lines)


__all__ = ["DATASET_PATH", "EvalCase", "CaseResult", "THRESHOLDS", "check_thresholds", "format_report", "load_dataset", "run_evaluation"]
