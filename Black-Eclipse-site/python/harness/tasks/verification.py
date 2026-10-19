"""Completion verification by task type — completion is evidence, not prose (W8.4).

The pre-W8 completion contract (`TaskManager.verify_completion`) checks durable
STATE: dependencies, required children, criteria a caller marked passed. Round
4's addition is the missing half: a task that declares a `taskType` must ALSO
pass a verifier for that type, which reads EVIDENCE the run actually produced —
the code-verification ledger's zero-exit records, delivered artifacts, recorded
sources, observed metrics — never the model's sentence.

`verify_task` is the ONE dispatch: it returns `None` for a task without a
`taskType`, so a task created before/outside the goal contract keeps the exact
pre-W8 completion contract. A verifier NEVER runs a tool or a model; it reads
records the runtime already wrote.

Evidence shape (from `bootstrap._outcome_from_dump`): a bounded dict of the run
result's own blobs — `codeVerification` (records/artifacts/reviews), `research`
(sources/claims), `documents`, `images` — plus the run's metrics. Attached task
artifacts (references, never bytes) ride beside it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .model import GoalContract, Task, TaskType

log = logging.getLogger("harness.tasks.verification")

_SPLIT_RE = re.compile(r"[^a-z0-9]+")

#: Record classes whose zero exit proves each check kind (mirrors
#: `code/verify.py::CLAIM_CLASSES`; duplicated deliberately so a policy edit
#: cannot silently widen a completion gate without touching this file).
CHECK_CLASSES: dict[str, tuple[str, ...]] = {
    "tests": ("unit_test", "python_test"),
    "build": ("build",),
    "typecheck": ("typecheck",),
    "lint": ("lint",),
    "format": ("format_check",),
}

#: The words in acceptance/deliverable text that require each record class.
#: Matched on word boundaries (never a raw substring), so "latest" is not a
#: "test" and "preformatted" is not a "format check".
_CHECK_SIGNALS: dict[str, tuple[str, ...]] = {
    "tests": ("test", "tests", "pytest", "vitest", "jest", "suite", "unit test"),
    "build": ("build", "builds", "build passes", "compiles", "bundle",
              "production build", "npm run build"),
    "typecheck": ("typecheck", "type check", "tsc", "types", "no type errors"),
    "lint": ("lint", "eslint", "ruff"),
    "format": ("format check", "prettier"),
}

#: Tokens too generic to prove a deliverable was actually delivered.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "into", "your", "its",
    "small", "simple", "basic", "little", "working", "complete", "full", "new",
    "app", "application", "program", "script", "file", "files", "code",
})


@dataclass
class VerificationCheck:
    """One evidence check: what was required, whether it held, and the proof."""

    name: str
    ok: bool
    detail: str = ""
    evidence: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "ok": self.ok, "detail": self.detail,
            "evidence": dict(self.evidence or {}),
        }


@dataclass
class TaskVerification:
    """The verdict for one task's evidence. `ok` requires EVERY check to hold."""

    task_type: str
    checks: list[VerificationCheck] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "taskType": self.task_type, "ok": self.ok,
            "checks": [c.to_dict() for c in self.checks],
            "missing": list(self.missing),
        }

    def summary(self) -> str:
        """A bounded, plain sentence naming what is missing (never the whole log)."""
        if self.ok:
            return f"{self.task_type} verification passed ({len(self.checks)} check(s))"
        return "verification failed: " + "; ".join(self.missing[:5])


@dataclass
class VerificationContext:
    """Everything a verifier may read. Records only — never the model's prose."""

    task: Task
    status: str = "completed"                 # the run's own terminal status
    evidence: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    output_reference: Optional[str] = None

    @property
    def contract(self) -> Optional[GoalContract]:
        return self.task.goal_contract


class TaskVerifier(Protocol):
    """A verifier for one task type. PURE apart from reading its context."""

    task_type: str

    def verify(self, ctx: VerificationContext) -> TaskVerification: ...


# ── Shared helpers ────────────────────────────────────────────────────────────


def _code_records(ctx: VerificationContext) -> list[dict[str, Any]]:
    blob = ctx.evidence.get("codeVerification")
    if not isinstance(blob, dict):
        return []
    records = blob.get("records")
    return [r for r in records if isinstance(r, dict)] if isinstance(records, list) else []


def _code_artifact_observations(ctx: VerificationContext) -> list[dict[str, Any]]:
    blob = ctx.evidence.get("codeVerification")
    if not isinstance(blob, dict):
        return []
    rows = blob.get("artifacts")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _passing(
    records: list[dict[str, Any]], classes: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        r for r in records
        if str(r.get("commandClass") or "") in classes and int(r.get("exitCode") or 0) == 0
    ]


def _contract_text(ctx: VerificationContext) -> str:
    """Acceptance + deliverable text, lowercased — the requirement vocabulary."""
    contract = ctx.contract
    if contract is None:
        return ""
    parts = list(contract.acceptance) + list(contract.deliverables)
    return " ".join(parts).lower()


def _contains(text: str, phrase: str) -> bool:
    if " " in phrase:
        return phrase in text
    return re.search(rf"\b{re.escape(phrase)}\b", text) is not None


def _required_checks(ctx: VerificationContext) -> list[str]:
    text = _contract_text(ctx)
    required: list[str] = []
    for kind, signals in _CHECK_SIGNALS.items():
        if any(_contains(text, signal) for signal in signals):
            required.append(kind)
    return required


def _artifact_tokens(ctx: VerificationContext) -> set[str]:
    tokens: set[str] = set()
    for artifact in ctx.artifacts:
        for key in ("label", "uri", "kind"):
            value = str(artifact.get(key) or "").lower()
            tokens.update(t for t in _tokenize(value) if t)
    for record in _code_artifact_observations(ctx):
        tokens.update(_tokenize(str(record.get("artifactName") or "").lower()))
    return tokens


def _tokenize(text: str) -> set[str]:
    return {t for t in _SPLIT_RE.split(text) if len(t) >= 4 and t not in _STOPWORDS}


def _deliverable_covered(deliverable: str, tokens: set[str]) -> bool:
    wanted = _tokenize(deliverable.lower())
    if not wanted:
        return bool(tokens)  # a generic phrase needs only SOME delivered artifact
    return bool(wanted & tokens)


# ── Verifiers ─────────────────────────────────────────────────────────────────


class CodeVerifier:
    """code ⇒ the run completed, its declared checks passed, artifacts delivered."""

    task_type = TaskType.CODE.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck(
            "run_completed", completed,
            "the run finished" if completed else f"the run ended {ctx.status}",
        ))
        if not completed:
            missing.append("the run did not complete")

        records = _code_records(ctx)
        for kind in _required_checks(ctx):
            classes = CHECK_CLASSES[kind]
            passing = _passing(records, classes)
            ok = bool(passing)
            checks.append(VerificationCheck(
                kind, ok,
                f"{kind} passed" if ok else f"no successful {kind} run was recorded",
                evidence={"recordClass": list(classes), "recordCount": len(passing)},
            ))
            if not ok:
                missing.append(f"no successful {kind} run was recorded")

        artifacts = list(ctx.artifacts) + _code_artifact_observations(ctx)
        tokens = _artifact_tokens(ctx)
        delivs = list((ctx.contract.deliverables if ctx.contract else []) or [])
        if delivs:
            for deliverable in delivs:
                covered = bool(artifacts) and _deliverable_covered(deliverable, tokens)
                checks.append(VerificationCheck(
                    f"deliverable:{deliverable[:60]}", covered,
                    "delivered" if covered else "no delivered artifact matches this deliverable",
                ))
                if not covered:
                    missing.append(f"deliverable {deliverable[:80]!r} has no delivered artifact")
        elif not artifacts:
            checks.append(VerificationCheck(
                "artifact_delivered", False, "no artifact was delivered",
            ))
            missing.append("no artifact was delivered")

        return TaskVerification(self.task_type, checks, missing)


class ResearchVerifier:
    """research ⇒ recorded sources back the result."""

    task_type = TaskType.RESEARCH.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        blob = ctx.evidence.get("research")
        sources = blob.get("sources") if isinstance(blob, dict) else None
        claims = blob.get("claims") if isinstance(blob, dict) else None
        source_count = len(sources) if isinstance(sources, list) else 0
        claim_count = len(claims) if isinstance(claims, list) else 0
        ok = source_count > 0
        checks.append(VerificationCheck(
            "sources", ok,
            f"{source_count} source(s) recorded" if ok else "no sources were recorded",
            evidence={"sources": source_count, "claims": claim_count},
        ))
        if not ok:
            missing.append("no sources were recorded for the research")
        return TaskVerification(self.task_type, checks, missing)


class DocumentVerifier:
    """document ⇒ the artifact (or the produced document record) exists."""

    task_type = TaskType.DOCUMENT.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        documents = ctx.evidence.get("documents")
        has_documents = isinstance(documents, dict) and bool(documents)
        ok = bool(ctx.artifacts) or has_documents
        checks.append(VerificationCheck(
            "document_delivered", ok,
            "a document artifact was delivered" if ok
            else "no document artifact was delivered",
            evidence={"artifacts": len(ctx.artifacts), "documents": has_documents},
        ))
        if not ok:
            missing.append("no document artifact was delivered")
        return TaskVerification(self.task_type, checks, missing)


class WorkflowVerifier:
    """workflow ⇒ the run did observable work and produced a result reference."""

    task_type = TaskType.WORKFLOW.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        tool_calls = int(ctx.metrics.get("toolCalls") or 0)
        acted = tool_calls > 0
        checks.append(VerificationCheck(
            "observed_steps", acted,
            f"{tool_calls} tool call(s) observed" if acted
            else "the workflow executed no steps",
            evidence={"toolCalls": tool_calls},
        ))
        if not acted:
            missing.append("the workflow executed no steps")

        has_result = bool(ctx.output_reference) or bool(str(ctx.evidence.get("output") or ""))
        checks.append(VerificationCheck(
            "result_reference", has_result,
            "a result reference was recorded" if has_result
            else "no result reference was recorded",
        ))
        if not has_result:
            missing.append("no result reference was recorded")
        return TaskVerification(self.task_type, checks, missing)


class FinanceVerifier:
    """finance ⇒ provenance evidence was recorded (sources/claims or advisory)."""

    task_type = TaskType.FINANCE.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        blob = ctx.evidence.get("research")
        sources = blob.get("sources") if isinstance(blob, dict) else None
        source_count = len(sources) if isinstance(sources, list) else 0
        ok = source_count > 0
        checks.append(VerificationCheck(
            "provenance", ok,
            f"{source_count} source(s) recorded" if ok
            else "no provenance evidence (sources) was recorded",
            evidence={"sources": source_count},
        ))
        if not ok:
            missing.append("no provenance evidence (sources) was recorded")
        return TaskVerification(self.task_type, checks, missing)


class GeneralVerifier:
    """general ⇒ a completed run with a recorded result reference or artifact."""

    task_type = TaskType.GENERAL.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        has_result = bool(ctx.output_reference) or bool(ctx.artifacts)
        checks.append(VerificationCheck(
            "result_recorded", has_result,
            "a result reference or artifact was recorded" if has_result
            else "no result reference or artifact was recorded",
        ))
        if not has_result:
            missing.append("no result reference or artifact was recorded")
        return TaskVerification(self.task_type, checks, missing)


# ── Registry + dispatch ───────────────────────────────────────────────────────

_VERIFIERS: dict[str, TaskVerifier] = {}


def register_verifier(verifier: TaskVerifier) -> None:
    """Register (or replace) the verifier for its task type."""
    _VERIFIERS[str(verifier.task_type)] = verifier


def get_verifier(task_type: str) -> Optional[TaskVerifier]:
    return _VERIFIERS.get(str(task_type))


def verify_task(
    task: Task,
    *,
    status: str,
    evidence: Optional[dict[str, Any]] = None,
    artifacts: Optional[list[dict[str, Any]]] = None,
    metrics: Optional[dict[str, Any]] = None,
) -> Optional[TaskVerification]:
    """Verify one task's evidence. `None` when the task declares no taskType.

    A declared taskType with no registered verifier is a REFUSAL, not a pass:
    the verdict reports the missing verifier so a misconfigured type can never
    silently complete (never a fabricated pass).
    """
    if task.task_type is None:
        return None
    ctx = VerificationContext(
        task=task, status=status, evidence=dict(evidence or {}),
        artifacts=list(artifacts or []), metrics=dict(metrics or {}),
        output_reference=task.output_reference,
    )
    verifier = get_verifier(task.task_type.value)
    if verifier is None:
        return TaskVerification(
            task.task_type.value,
            [VerificationCheck("verifier_registered", False,
                               f"no verifier is registered for {task.task_type.value}")],
            [f"no verifier is registered for task type {task.task_type.value!r}"],
        )
    try:
        return verifier.verify(ctx)
    except Exception as exc:  # noqa: BLE001 - a verifier crash is a refusal, not a pass
        log.warning("verifier for %s crashed", task.task_type.value, exc_info=True)
        return TaskVerification(
            task.task_type.value,
            [VerificationCheck("verifier_ran", False, f"the verifier failed: {exc}")],
            [f"the {task.task_type.value} verifier failed to run"],
        )


for _verifier in (
    CodeVerifier(), ResearchVerifier(), DocumentVerifier(),
    WorkflowVerifier(), FinanceVerifier(), GeneralVerifier(),
):
    register_verifier(_verifier)


__all__ = [
    "CHECK_CLASSES",
    "CodeVerifier",
    "DocumentVerifier",
    "FinanceVerifier",
    "GeneralVerifier",
    "ResearchVerifier",
    "TaskVerification",
    "TaskVerifier",
    "VerificationCheck",
    "VerificationContext",
    "WorkflowVerifier",
    "get_verifier",
    "register_verifier",
    "verify_task",
]
