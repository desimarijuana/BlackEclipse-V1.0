"""Turn a RECORDED recurrence into an INERT candidate. Nothing else.

A mistake is an observation (`eclipse_memory/mistakes.py`). This module is the one
place where an observation that keeps happening becomes a *proposal*. The proposal
is inert: it names a target and a set of structured operations, and it changes
nothing until activation succeeds through `skills/versioning.py`.

Two rules copied, not invented: recurrence is required (one occurrence is never
evidence — `skills/learning.py`), and no model call decides whether a candidate
exists (mirrors `research/claims.py` and `code/verify.py`).

The module owns the BUDGET, the NARROWING (the frozen set) and the AGGREGATION of
evaluation evidence — never a second lifecycle, a second recurrence counter, or a
second agent loop.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..persistence import now_iso
from ..skills.patches import FORBIDDEN_FIELDS
from . import policy
from .evolution_store import EvolutionStore

# A category must be observed this many times before it is evidence at all.
RECURRENCE_THRESHOLD = 3
MAX_CANDIDATES_PER_SCAN = 20   # a scan is a bounded window, not a replay

# Which mistake categories can propose a code change, and to what kind of target.
# A category absent from this table never yields a candidate — the absence is the
# policy, so it is DATA.
CATEGORY_TARGETS: dict[str, str] = {
    "invalid_output_schema": "the schema/validator that rejected the output",
    "incorrect_tool_arguments": "the tool argument validation that accepted a bad call",
    "repeated_failure": "the retry/fallback path that kept failing",
    "timeout": "the bound that timed out",
    "unresolved_contradiction": "the comparison rule that missed a conflict",
    "currency_mismatch": "the unit/currency normalisation step",
    "unit_mismatch": "the unit/currency normalisation step",
    "capability_failure": "the generated capability whose contract or execution failed",
}

# The four non-patchable authorities — a subject cannot edit its own judge. A
# proposal that touches one is REFUSED with a structured code, never skipped.
FROZEN_PATHS: tuple[str, ...] = (
    "python/harness/code/policy.py",
    "python/harness/skills/permissions.py",
    "python/harness/mcp/approvals.py",
    "scripts/check-all.js",
)

# Refusal codes (stable, testable).
FROZEN_PATH = "FROZEN_PATH"
PROTECTED = "PROTECTED"
FORBIDDEN_FIELD = "FORBIDDEN_FIELD"
OUTSIDE_WORKSPACE = "OUTSIDE_WORKSPACE"
NOT_PATCHABLE = "NOT_PATCHABLE"

# The frozen files' basenames, matched case-insensitively against a normalised
# POSIX path so `./python/harness/code/policy.py` still refuses.
_FROZEN_NORMALISED = {p.replace("\\", "/").casefold() for p in FROZEN_PATHS}
# FORBIDDEN_FIELDS from skills/patches.py, as data (identity / permissions / tools /
# risk). A code proposal may never set one.
_CODE_FORBIDDEN_FIELDS = frozenset(FORBIDDEN_FIELDS)


class EvolutionRefusal(Exception):
    """A refusal with a STRUCTURED reason — never a bare ValueError."""

    def __init__(self, code: str, *, path: Optional[str] = None, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.path = path
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


# ── The recurrence bridge (§6.1) ─────────────────────────────────────────────


def _signature(category: str, problem: str) -> str:
    """A deterministic candidate signature (category + normalised problem)."""
    raw = f"{category}|{problem.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _problem_statement(category: str, target_kind: str, observed: int) -> str:
    """A plain, bounded, non-secret problem sentence (never a path or a digest)."""
    return (
        f"Eclipse hit the same problem {observed} times: {target_kind}. "
        f"(category: {category})"
    )[:1000]


def _category_signature(category: str) -> str:
    """The recurrence-ledger key for a category (deterministic, category-scoped).

    `skills/learning._candidate_recurrence_key` keys on tool evidence; a mistake
    category's recurrence is keyed here so the SAME ledger (`LearningRecurrence`)
    is the counter — this phase never maintains a rival count.
    """
    return hashlib.sha256(f"mistake|{category}".encode("utf-8")).hexdigest()[:32]


def record_mistake_recurrence(
    run_store: Any,
    categories: Any,
    run_id: Optional[str] = None,
) -> dict[str, int]:
    """Write one recurrence per mistake category into the ONE ledger.

    This is the production trigger the bridge reads: `record_learning_recurrence`
    dedupes on `(runId, signature)`, so re-analysing the same run cannot inflate a
    category. No model call, no candidate, no second counter.
    """
    counts: dict[str, int] = {}
    if run_store is None:
        return counts
    seen = {
        str(category).strip()
        for category in (categories or ())
        if str(category).strip()
    }
    for category in sorted(seen):
        try:
            counts[category] = int(
                run_store.record_learning_recurrence(
                    _category_signature(category), run_id,
                )
            )
        except Exception:  # noqa: BLE001 - observation must never break analysis
            continue
    return counts


def candidates_from_mistakes(
    *,
    store: Any,
    since_iso: str,
    db: Any = None,
    max_candidates: int = MAX_CANDIDATES_PER_SCAN,
    created_by_run_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Return INERT candidates for eligible categories whose recurrence crosses
    RECURRENCE_THRESHOLD.

    Recurrence is read from the ONE ledger (`LearningRecurrence`, category-scoped)
    in `agent-memory.db` — the same counter `skills/learning.py` reads, never a
    rival count.

    Never creates a candidate: for a category missing from CATEGORY_TARGETS; from
    a single occurrence; when an identical signature already has one (dedupe on
    `signature`). READ-ONLY against the mistake tables: the only write is a
    candidate row.
    """
    evolution = EvolutionStore(store)
    connection = db if db is not None else store._db  # noqa: SLF001 - the one shared connection

    # The ONE counter: the recurrence ledger, category-scoped.
    ledger_counts: dict[str, int] = {}
    try:
        for category in CATEGORY_TARGETS:
            row = connection.execute(
                "SELECT seenCount FROM LearningRecurrence WHERE signature=?",
                (_category_signature(category),),
            ).fetchone()
            if row:
                ledger_counts[category] = int(row["seenCount"])
    except Exception:  # noqa: BLE001 - a missing table is simply no recurrence
        ledger_counts = {}

    created: list[dict[str, Any]] = []
    for category, target_kind in CATEGORY_TARGETS.items():
        if len(created) >= max_candidates:
            break
        observed = ledger_counts.get(category, 0)
        if observed < RECURRENCE_THRESHOLD:
            continue
        signature = _signature(category, target_kind)
        if evolution.get_by_signature(signature) is not None:
            continue  # dedupe: one candidate per signature
        created.append(evolution.save_candidate({
            "signature": signature,
            "sourceCategory": category,
            "observedCount": observed,
            "problemStatement": _problem_statement(category, target_kind, observed),
            "targetPath": None,
            "status": "inert",
            "createdByRunId": created_by_run_id,
        }))
    return created


# ── The proposal (§6.3) ──────────────────────────────────────────────────────


def _normalise(path: str) -> str:
    text = str(path).replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text


def is_frozen(path: str) -> bool:
    return _normalise(path).casefold() in _FROZEN_NORMALISED


def propose_ops(
    candidate: dict[str, Any],
    *,
    actor: Any,
    ops: Optional[list[dict[str, Any]]] = None,
) -> list[dict[str, Any]]:
    """Build and validate the structured ops for a candidate.

    Refuses with `EvolutionRefusal` and a code when: FROZEN_PATH (the target is one
    of the four frozen files); PROTECTED (`policy.is_protected` for another
    reason); FORBIDDEN_FIELD (the ops would set identity, permissions, a tool
    allowlist or a risk class); OUTSIDE_WORKSPACE (`policy.resolve_within`
    rejects the target); NOT_PATCHABLE (the op set is empty or names an op
    `code/patch.py` rejects).

    Performs NO model call; a model-assisted proposal produces ops this function
    validates.
    """
    target = _normalise(str(candidate.get("targetPath") or ""))
    if not target:
        raise EvolutionRefusal(NOT_PATCHABLE, detail="no target path was named")

    if is_frozen(target):
        raise EvolutionRefusal(
            FROZEN_PATH, path=target,
            detail="that file decides what Eclipse is allowed to do, so Eclipse can't change it",
        )
    # Protected paths are refused for the same class of reason (a database, .env,
    # migrations, .git). `is_protected` takes a workspace-relative-ish path.
    if policy.is_protected(target):
        raise EvolutionRefusal(
            PROTECTED, path=target,
            detail="that file is part of Eclipse's own data and can't be changed by a task",
        )
    # Outside the bound workspace: `resolve_within` compares REAL paths.
    root = _workspace_root()
    if root is not None:
        try:
            policy.resolve_within(root, target)
        except policy.PolicyDenial as denial:
            raise EvolutionRefusal(OUTSIDE_WORKSPACE, path=target, detail=denial.reason) from denial

    proposed = ops if ops is not None else (candidate.get("proposedOps") or [])
    if not proposed:
        raise EvolutionRefusal(NOT_PATCHABLE, path=target, detail="no change was proposed")

    validated: list[dict[str, Any]] = []
    for op in proposed:
        if not isinstance(op, dict) or op.get("op") not in ("create", "replace", "delete", "move"):
            raise EvolutionRefusal(NOT_PATCHABLE, path=target, detail=f"unsupported op {op!r}")
        # A patch may never set a forbidden (authority) field. The op's `path` is a
        # JSON-ish field name here; check its first token against the set.
        for key in ("path", "fromPath"):
            value = op.get(key)
            if value and str(value).split("/")[0].split(".")[0] in _CODE_FORBIDDEN_FIELDS:
                raise EvolutionRefusal(
                    FORBIDDEN_FIELD, path=target,
                    detail=f"a change may not set {value!r}",
                )
        for forbidden in _CODE_FORBIDDEN_FIELDS:
            if op.get("field") == forbidden or op.get("target") == forbidden:
                raise EvolutionRefusal(
                    FORBIDDEN_FIELD, path=target, detail=f"a change may not set {forbidden!r}",
                )
        validated.append(dict(op))
    return validated


def _workspace_root() -> Optional[Path]:
    try:
        from .workspace import default_root  # noqa: PLC0415

        return default_root()
    except Exception:  # noqa: BLE001 - no root is simply no confinement check
        return None


# ── Evaluation (§6.4) ────────────────────────────────────────────────────────


@dataclass
class CheckOutcome:
    command_class: str
    passed: bool
    exit_code: Optional[int]
    execution_id: str = ""
    reason: str = ""


@dataclass
class EvaluationReport:
    candidateId: str
    targetPath: str
    checks: list[CheckOutcome] = field(default_factory=list)
    ledgerExecutionIds: list[str] = field(default_factory=list)
    passed: bool = False
    regression: bool = False
    unmeasured: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidateId": self.candidateId, "targetPath": self.targetPath,
            "checks": [c.__dict__ for c in self.checks],
            "ledgerExecutionIds": self.ledgerExecutionIds,
            "passed": self.passed, "regression": self.regression,
            "unmeasured": self.unmeasured,
        }


def owning_test_paths(target_path: str) -> list[str]:
    """The test file(s) that own a target, DERIVED from the path — never guessed.

    A python module `python/harness/x/y.py` → `python/tests/test_y.py`; a kit file
    under `python/harness/code/kits/<id>/` → `python/tests/test_kit_<id>.py`; a TS
    module `src/lib/a/b.ts` → `src/lib/a/b.test.ts`. When nothing is derivable the
    list is empty and the caller records it as an unmeasured dimension.
    """
    rel = _normalise(target_path)
    if not rel:
        return []
    # Kit acceptance test.
    marker = "python/harness/code/kits/"
    if rel.startswith(marker):
        rest = rel[len(marker):]
        kit_id = rest.split("/", 1)[0]
        return [f"python/tests/test_kit_{kit_id}.py"]
    name = rel.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if rel.endswith(".py"):
        return [f"python/tests/test_{stem}.py"]
    if rel.endswith(".ts") and not rel.endswith(".test.ts"):
        return [rel[:-3] + ".test.ts"]
    return []


def evaluate_candidate(
    candidate: dict[str, Any],
    *,
    run_check: Any,
    base_digest: Optional[str] = None,
) -> EvaluationReport:
    """Run the owning checks and record every execution.

    `run_check(command_class, paths) -> dict` is the ONE execution seam (the
    handler supplies it from the Phase 3 command broker + Phase 4 ledger). The
    outcome is DETERMINISTIC: a check passes only when its exit code is zero.
    """
    target = str(candidate.get("targetPath") or "")
    report = EvaluationReport(candidateId=str(candidate.get("id") or ""), targetPath=target)
    tests = owning_test_paths(target)
    if not tests:
        report.unmeasured.append("owning test")
        report.passed = False
        return report
    for path in tests:
        outcome = run_check(path)
        passed = bool(outcome.get("exitCode") == 0)
        report.checks.append(CheckOutcome(
            command_class=str(outcome.get("commandClass") or "python_test"),
            passed=passed, exit_code=outcome.get("exitCode"),
            execution_id=str(outcome.get("executionId") or ""),
            reason=str(outcome.get("reason") or ""),
        ))
        if outcome.get("executionId"):
            report.ledgerExecutionIds.append(str(outcome["executionId"]))
        if not passed:
            report.regression = report.regression or bool(base_digest and outcome.get("previouslyPassed"))
    report.passed = bool(report.checks) and all(c.passed for c in report.checks)
    return report


# ── The versioning adapter (§6.5) ────────────────────────────────────────────


def candidate_skill_manifest(candidate: dict[str, Any]) -> dict[str, Any]:
    """A skill-shaped subject for the code candidate, for `skills/versioning.py`.

    A code change is carried as the skill's patchable `instructions` field (the
    proposed bytes as a data block), so the EXISTING lifecycle validates it without
    editing `versioning.py`. The skill id names the code subject; identity,
    permissions, tools and risk are never set by the proposal (FORBIDDEN_FIELDS).
    """
    sid = "code.subject." + _signature(str(candidate.get("sourceCategory") or ""), str(candidate.get("targetPath") or ""))
    return {
        "id": sid,
        "name": f"Code subject {candidate.get('targetPath')}",
        "version": "1.0.0",
        "description": str(candidate.get("problemStatement") or "a repeated code problem")[:2000],
        "category": "system",
        "status": "draft",
        "instructions": "SKILL.md",
        "inputSchema": {"type": "object", "properties": {}},
        "requiredTools": [],
        "requiredSkills": [],
        "permissions": [],
        "riskLevel": "low",
        "limits": {"maxSteps": 4, "timeoutMs": 60000, "maxToolCalls": 8},
        "author": "eclipse",
        # `author`, not `learning`: this is a managed code subject for the
        # existing lifecycle, not a skill learned from a run. It carries no
        # permissions/tools/risk (FORBIDDEN_FIELDS).
        "origin": "author",
    }


# ── The archive + honest metrics (§6.6) ──────────────────────────────────────


def archive_metrics(store: Any, window_days: int = 90) -> dict[str, Any]:
    """Every metric is derived from EvolutionAttempt + RSL EvaluationRun rows.

    A metric whose inputs do not exist (no completed attempts, no cost rows)
    renders the string "UNKNOWN" — NEVER 0, and never a blended score. The
    `rsl_*` block is measured from persisted RSL experiment runs; its missing
    inputs are `None` (UNMEASURED).
    """
    evolution = EvolutionStore(store)
    db = store._db  # noqa: SLF001
    from ..evaluation.repair_metrics import (  # noqa: PLC0415 - avoid an import cycle
        metrics_from_rsl_runs,
        rsl_runs_from_store,
    )

    rsl_metrics = metrics_from_rsl_runs(rsl_runs_from_store(store, limit=500))

    cutoff = _days_ago(window_days)
    rows = db.execute(
        "SELECT a.outcome, a.costMicros, a.tokensUsed, c.sourceCategory "
        "FROM EvolutionAttempt a JOIN EvolutionCandidate c ON c.id = a.candidateId "
        "WHERE a.startedAt >= ?",
        (cutoff,),
    ).fetchall()

    attempts = len(rows)
    unmeasured: list[str] = []
    if attempts == 0:
        return {
            "attempts": 0, "successRate": "UNKNOWN", "regressionRate": "UNKNOWN",
            "rollbackCount": 0, "costPerSuccess": "UNKNOWN",
            "cost_per_success": "UNKNOWN",
            **rsl_metrics,
            "perCategory": {}, "unmeasured": ["successRate", "regressionRate", "costPerSuccess"],
        }

    successes = sum(1 for r in rows if r["outcome"] == "success")
    rollbacks = sum(1 for r in rows if r["outcome"] == "rolled_back")
    failures = sum(1 for r in rows if r["outcome"] == "failure")

    success_rate: Any = round(successes / attempts, 4)
    regression_rate: Any = round(rollbacks / attempts, 4)

    costs = [r["costMicros"] for r in rows if r["costMicros"] is not None]
    if len(costs) < attempts:
        cost_per_success: Any = "UNKNOWN"
        unmeasured.append("costPerSuccess")
    elif successes == 0:
        cost_per_success = "UNKNOWN"
        unmeasured.append("costPerSuccess")
    else:
        cost_per_success = round(sum(costs) / successes, 2)

    per_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        category = row["sourceCategory"] or "unknown"
        bucket = per_category.setdefault(category, {"attempts": 0, "successes": 0, "rollbacks": 0})
        bucket["attempts"] += 1
        if row["outcome"] == "success":
            bucket["successes"] += 1
        if row["outcome"] == "rolled_back":
            bucket["rollbacks"] += 1

    return {
        "attempts": attempts,
        "successRate": success_rate,
        "regressionRate": regression_rate,
        "rollbackCount": rollbacks,
        "failureCount": failures,
        "costPerSuccess": cost_per_success,
        "cost_per_success": cost_per_success,
        **rsl_metrics,
        "perCategory": per_category,
        "unmeasured": unmeasured,
    }


def _days_ago(days: int) -> str:
    import datetime as _dt  # noqa: PLC0415

    then = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=max(0, int(days)))
    return then.strftime("%Y-%m-%dT%H:%M:%S") + ".000Z"


__all__ = [
    "CATEGORY_TARGETS",
    "EvolutionRefusal",
    "EvaluationReport",
    "CheckOutcome",
    "FROZEN_PATH",
    "FROZEN_PATHS",
    "FORBIDDEN_FIELD",
    "MAX_CANDIDATES_PER_SCAN",
    "NOT_PATCHABLE",
    "OUTSIDE_WORKSPACE",
    "PROTECTED",
    "RECURRENCE_THRESHOLD",
    "archive_metrics",
    "candidate_skill_manifest",
    "candidates_from_mistakes",
    "evaluate_candidate",
    "is_frozen",
    "owning_test_paths",
    "propose_ops",
    "record_mistake_recurrence",
]
