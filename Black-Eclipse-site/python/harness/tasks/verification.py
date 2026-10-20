"""Completion verification by task type — completion is evidence, not prose (W8.4/W14).

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

Round 4 W14 unified the evidence contract. The verifiers now read the shapes
the runtime REALLY writes, and each task type's rule is the one the roadmap
states (`docs/harness/self-evolution-roadmap.md`, W14):

| task type | the evidence that must exist |
|---|---|
| `code`     | the run completed, its declared checks passed, the deliverables landed |
| `research` | traceable sources, a claim backed by evidence, the uncertainty recorded |
| `document` | the artifact AND the sections the contract required |
| `workflow` | observed steps AND an observable state change |
| `finance`  | provenance, freshness and claim-to-evidence (the Evidence Engine rules) |
| `data`     | a reproducible calculation: a pinned program and its inputs |
| `general`  | a recorded result reference or artifact |

Two research evidence shapes exist and both are read: the ordinary run's
collected blob (`source_collector.to_research_blob()` → `metadata.citations`,
`collectedSources`, `failedRoutes`, `financeAnalysis`) and the gated run's
blob (`status`, `validation.claims`, `coverage`, `budget`, `stopReasonText` and
a `receipt` with `evidenceRefs`). The flat `sources`/`claims` shape the first
draft read was never produced by the runtime, so it is not read here.

Evidence shape (from `bootstrap._outcome_from_dump`): a bounded dict of the run
result's own blobs — `codeVerification` (records/artifacts/reviews), `research`
(sources/claims), `documents`, `images`, `analyses` — plus the run's metrics.
Attached task artifacts (references, never bytes) ride beside it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from .goal import parse_required_sections
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


# ── Real evidence readers (W14) ───────────────────────────────────────────────


def _research_blob(ctx: VerificationContext) -> dict[str, Any]:
    blob = ctx.evidence.get("research")
    return blob if isinstance(blob, dict) else {}


def _evidence_refs(blob: dict[str, Any]) -> list[dict[str, Any]]:
    """Every evidence reference the run recorded (both research shapes)."""
    refs: list[dict[str, Any]] = []
    receipt = blob.get("receipt")
    if isinstance(receipt, dict):
        refs += [r for r in receipt.get("evidenceRefs") or [] if isinstance(r, dict)]
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        refs += [c for c in metadata.get("citations") or [] if isinstance(c, dict)]
    refs += [s for s in blob.get("collectedSources") or [] if isinstance(s, dict)]
    return refs


def _is_traceable(ref: dict[str, Any]) -> bool:
    """A reference a reader could follow: an evidence id, a URL or a source."""
    return any(
        str(ref.get(key) or "").strip()
        for key in ("evidenceId", "id", "url", "source", "canonicalUrl", "hash", "name")
    )


def _recorded_claims(blob: dict[str, Any]) -> list[dict[str, Any]]:
    """The claims the run recorded (gated validation + the receipt's copy)."""
    claims: list[dict[str, Any]] = []
    validation = blob.get("validation")
    if isinstance(validation, dict):
        claims += [c for c in validation.get("claims") or [] if isinstance(c, dict)]
    receipt = blob.get("receipt")
    if isinstance(receipt, dict):
        claims += [c for c in receipt.get("claims") or [] if isinstance(c, dict)]
    return claims


def _supported_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Claims that are BOTH supported and tied to recorded evidence."""
    return [
        c for c in claims
        if str(c.get("supportStatus") or "") == "supported" and c.get("evidenceIds")
    ]


def _recorded_gaps(blob: dict[str, Any]) -> list[str]:
    """The uncertainty the run RECORDED (unresolved facts, failed routes, limits)."""
    gaps: list[str] = []
    validation = blob.get("validation")
    if isinstance(validation, dict):
        gaps += [str(g) for g in validation.get("unresolved") or [] if str(g).strip()]
    receipt = blob.get("receipt")
    if isinstance(receipt, dict):
        gaps += [str(g) for g in receipt.get("validationIssues") or [] if str(g).strip()]
    gaps += [str(g) for g in blob.get("failedRoutes") or [] if str(g).strip()]
    if str(blob.get("stopReasonText") or "").strip():
        gaps.append(str(blob.get("stopReasonText")).strip())
    metadata = blob.get("metadata")
    if isinstance(metadata, dict):
        gaps += [str(g) for g in metadata.get("missingEvidence") or [] if str(g).strip()]
        gaps += [str(g) for g in metadata.get("limitations") or [] if str(g).strip()]
    return gaps


def _temporal_stamps(blob: dict[str, Any]) -> list[str]:
    """When the recorded evidence is from — the freshness coordinates."""
    stamps: list[str] = []
    receipt = blob.get("receipt")
    if isinstance(receipt, dict):
        temporal = receipt.get("temporalStatus")
        if isinstance(temporal, dict) and str(temporal.get("asOf") or "").strip():
            stamps.append(str(temporal["asOf"]))
    for ref in _evidence_refs(blob):
        for key in ("publishedAt", "retrievedAt", "fiscalPeriod"):
            if str(ref.get(key) or "").strip():
                stamps.append(str(ref[key]))
    metadata = blob.get("metadata")
    if isinstance(metadata, dict) and str(metadata.get("asOf") or "").strip():
        stamps.append(str(metadata["asOf"]))
    return stamps


def _finance_facts(blob: dict[str, Any]) -> list[dict[str, Any]]:
    """The ordinary run's retrieved financial facts (with their own provenance)."""
    analysis = blob.get("financeAnalysis")
    if not isinstance(analysis, dict):
        return []
    return [f for f in analysis.get("facts") or [] if isinstance(f, dict)]


def _document_records(documents: Any) -> list[dict[str, Any]]:
    """Every document the run recorded (processed + authored); failures aside."""
    if not isinstance(documents, dict):
        return []
    rows = [d for d in documents.get("documents") or [] if isinstance(d, dict)]
    rows += [d for d in documents.get("authored") or [] if isinstance(d, dict)]
    return [
        d for d in rows
        if str(d.get("state") or "").upper() not in ("FAILED", "ERROR")
    ]


def _recorded_section_titles(records: list[dict[str, Any]]) -> list[str]:
    """The section titles a delivered document RECORDED (never its prose)."""
    titles: list[str] = []
    for record in records:
        for title in record.get("sectionTitles") or []:
            if str(title or "").strip():
                titles.append(str(title).strip())
        context = record.get("currentContext")
        if isinstance(context, dict) and str(context.get("section") or "").strip():
            titles.append(str(context["section"]).strip())
    return titles


def _section_present(name: str, titles: list[str]) -> bool:
    wanted = name.strip().lower()
    if not wanted:
        return True
    for title in titles:
        lowered = title.strip().lower()
        if lowered == wanted or wanted in lowered or lowered in wanted:
            return True
    return False


def _required_sections(ctx: VerificationContext) -> list[str]:
    """The sections the CONTRACT required (its acceptance/deliverable text)."""
    contract = ctx.contract
    if contract is None:
        return []
    text = " ".join(list(contract.acceptance) + list(contract.deliverables))
    return parse_required_sections(text)


def _research_calculations(ctx: VerificationContext) -> list[dict[str, Any]]:
    """The research engine's calculation records (formula + inputs + verdict)."""
    metadata = _research_blob(ctx).get("metadata")
    if not isinstance(metadata, dict):
        return []
    return [c for c in metadata.get("calculations") or [] if isinstance(c, dict)]


def _analysis_records(ctx: VerificationContext) -> list[dict[str, Any]]:
    """The sandbox analyses this run recorded (program digest + input digests)."""
    analyses = ctx.evidence.get("analyses")
    if not isinstance(analyses, dict):
        return []
    return [a for a in analyses.get("records") or [] if isinstance(a, dict)]


def _reproducible_records(ctx: VerificationContext) -> list[dict[str, Any]]:
    """Records that pin a computation AND its inputs (W14: data ⇒ reproducible).

    A calculation counts when it completed (`OK`), names its formula, and
    carries its inputs (values or evidence ids). An analysis counts when it
    completed, pins the program it ran (`sourceDigest`), pinned the inputs it
    read (`inputDigests`) and produced outputs.
    """
    out: list[dict[str, Any]] = []
    for calc in _research_calculations(ctx):
        if str(calc.get("status") or "").upper() != "OK":
            continue
        if not str(calc.get("formula") or "").strip():
            continue
        if not (calc.get("inputs") or calc.get("inputEvidenceIds")):
            continue
        out.append(calc)
    for record in _analysis_records(ctx):
        if str(record.get("status") or "") != "ok":
            continue
        if not str(record.get("sourceDigest") or "").strip():
            continue
        if not record.get("inputDigests"):
            continue
        if not record.get("outputs"):
            continue
        out.append(record)
    return out


def _observed_state(ctx: VerificationContext) -> list[str]:
    """The observable state a run left behind (never the model's sentence)."""
    seen: list[str] = []
    if ctx.artifacts:
        seen.append("artifacts")
    if _document_records(ctx.evidence.get("documents")):
        seen.append("documents")
    analyses = ctx.evidence.get("analyses")
    if isinstance(analyses, dict) and analyses.get("records"):
        seen.append("analyses")
    capability = ctx.evidence.get("capability")
    if isinstance(capability, dict) and capability:
        seen.append("capability")
    if _code_records(ctx):
        seen.append("code records")
    if _evidence_refs(_research_blob(ctx)):
        seen.append("sources")
    return seen


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
    """research ⇒ traceable sources, a claim backed by evidence, honest gaps.

    A confident sentence with no source, a claim nobody can follow, or a
    partial answer that hides its open gap all fail here: the uncertainty must
    be RECORDED, not merely implied.
    """

    task_type = TaskType.RESEARCH.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        blob = _research_blob(ctx)
        refs = [r for r in _evidence_refs(blob) if _is_traceable(r)]
        checks.append(VerificationCheck(
            "sources", bool(refs),
            f"{len(refs)} traceable source(s) recorded" if refs
            else "no traceable source was recorded",
            evidence={"sources": len(refs)},
        ))
        if not refs:
            missing.append("no traceable source was recorded")

        status = str(blob.get("status") or "")
        if status == "rejected":
            checks.append(VerificationCheck(
                "engine_verdict", False, "the research flow rejected the answer",
            ))
            missing.append("the research flow rejected the answer")
        else:
            checks.append(VerificationCheck(
                "engine_verdict", True, f"the research flow returned {status or 'no verdict'}",
            ))

        claims = _recorded_claims(blob)
        if isinstance(blob.get("validation"), dict):
            supported = _supported_claims(claims)
            checks.append(VerificationCheck(
                "claim_to_evidence", bool(supported),
                f"{len(supported)} claim(s) supported by recorded evidence" if supported
                else "no claim is supported by recorded evidence",
                evidence={"claims": len(claims), "supported": len(supported)},
            ))
            if not supported:
                missing.append("no claim is supported by recorded evidence")

        gaps = _recorded_gaps(blob)
        if status == "partial":
            checks.append(VerificationCheck(
                "uncertainty", bool(gaps),
                f"{len(gaps)} open gap(s) recorded" if gaps
                else "a partial answer recorded no open gap",
                evidence={"gaps": len(gaps)},
            ))
            if not gaps:
                missing.append("a partial research answer recorded no open gap")
        else:
            checks.append(VerificationCheck(
                "uncertainty", True,
                f"{len(gaps)} gap(s) recorded" if gaps else "no open gap was recorded",
                evidence={"gaps": len(gaps)},
            ))

        return TaskVerification(self.task_type, checks, missing)


class DocumentVerifier:
    """document ⇒ the artifact AND the sections the contract required (W14).

    The artifact alone is not proof of contents: when the contract names the
    sections, each named section must appear in the structure the delivered
    document RECORDED. A document that recorded no structure cannot prove its
    sections either — that is a refusal, not a pass.
    """

    task_type = TaskType.DOCUMENT.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        records = _document_records(ctx.evidence.get("documents"))
        delivered = bool(ctx.artifacts) or bool(records)
        checks.append(VerificationCheck(
            "document_delivered", delivered,
            "a document artifact was delivered" if delivered
            else "no document artifact was delivered",
            evidence={"artifacts": len(ctx.artifacts), "documents": len(records)},
        ))
        if not delivered:
            missing.append("no document artifact was delivered")

        required = _required_sections(ctx)
        if not required:
            checks.append(VerificationCheck(
                "required_sections", True, "the contract named no required section",
            ))
        else:
            titles = _recorded_section_titles(records)
            if not titles:
                checks.append(VerificationCheck(
                    "required_sections", False,
                    "the delivered document recorded no sections, so its required "
                    "sections could not be verified",
                    evidence={"required": list(required), "recorded": 0},
                ))
                missing.append(
                    "the delivered document recorded no sections, so its required "
                    "sections could not be verified"
                )
            else:
                absent = [name for name in required if not _section_present(name, titles)]
                checks.append(VerificationCheck(
                    "required_sections", not absent,
                    "every required section was recorded" if not absent
                    else f"missing section(s): {', '.join(absent)}",
                    evidence={"required": list(required), "recorded": len(titles)},
                ))
                for name in absent:
                    missing.append(f"the document is missing the required section {name!r}")

        return TaskVerification(self.task_type, checks, missing)


class WorkflowVerifier:
    """workflow ⇒ the run OBSERVED work and left an observable state (W14).

    The first draft accepted the run id as a "result reference" — the scheduler
    always records the run id, so a workflow that started, called one tool and
    produced nothing passed. The state must now be an OBSERVED record.
    """

    task_type = TaskType.WORKFLOW.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
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

        state = _observed_state(ctx)
        checks.append(VerificationCheck(
            "resulting_state", bool(state),
            f"observed: {', '.join(state)}" if state
            else "the workflow produced no observable state change",
            evidence={"observed": list(state)},
        ))
        if not state:
            missing.append("the workflow produced no observable state change")

        return TaskVerification(self.task_type, checks, missing)


class FinanceVerifier:
    """finance ⇒ provenance, freshness and claim-to-evidence (W14).

    The Evidence Engine stays the financial authority: this verifier reads the
    engine's own records (receipt refs, validation claims, its verdict) and
    NEVER re-derives a value. A rejected engine verdict is a refusal here too.
    """

    task_type = TaskType.FINANCE.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        blob = _research_blob(ctx)
        refs = [r for r in _evidence_refs(blob) if _is_traceable(r)]
        checks.append(VerificationCheck(
            "provenance", bool(refs),
            f"{len(refs)} source(s) recorded" if refs
            else "no provenance evidence (sources) was recorded",
            evidence={"sources": len(refs)},
        ))
        if not refs:
            missing.append("no provenance evidence (sources) was recorded")

        stamps = _temporal_stamps(blob)
        facts = _finance_facts(blob)
        period_facts = [f for f in facts if str(f.get("period") or "").strip()]
        fresh = bool(stamps) or bool(period_facts)
        checks.append(VerificationCheck(
            "freshness", fresh,
            f"{len(stamps)} freshness stamp(s) recorded" if stamps
            else (f"{len(period_facts)} fact period(s) recorded" if period_facts
                  else "no freshness evidence (when the data is from) was recorded"),
            evidence={"stamps": len(stamps), "periods": len(period_facts)},
        ))
        if not fresh:
            missing.append("no freshness evidence (when the data is from) was recorded")

        if facts:
            sourced = [f for f in facts if str(f.get("source") or "").strip()]
            checks.append(VerificationCheck(
                "fact_sources", bool(sourced),
                f"{len(sourced)}/{len(facts)} fact(s) carry a source" if sourced
                else "a financial fact carries no source",
                evidence={"facts": len(facts), "sourced": len(sourced)},
            ))
            if not sourced:
                missing.append("a financial fact carries no source")

        claims = _recorded_claims(blob)
        if isinstance(blob.get("validation"), dict):
            supported = _supported_claims(claims)
            checks.append(VerificationCheck(
                "claim_to_evidence", bool(supported),
                f"{len(supported)} claim(s) supported by recorded evidence" if supported
                else "no financial claim is supported by recorded evidence",
                evidence={"claims": len(claims), "supported": len(supported)},
            ))
            if not supported:
                missing.append("no financial claim is supported by recorded evidence")

        status = str(blob.get("status") or "")
        if status == "rejected":
            checks.append(VerificationCheck(
                "engine_verdict", False, "the evidence engine rejected the answer",
            ))
            missing.append("the evidence engine rejected the answer")
        else:
            checks.append(VerificationCheck(
                "engine_verdict", True, f"the evidence engine returned {status or 'no verdict'}",
            ))

        return TaskVerification(self.task_type, checks, missing)


class DataVerifier:
    """data ⇒ a reproducible calculation (W14).

    A number in prose is not a computation. The run must have RECORDED one: a
    calculation with its formula and inputs, or an analysis that pinned the
    program it ran and the inputs it read.
    """

    task_type = TaskType.DATA.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        records = _reproducible_records(ctx)
        checks.append(VerificationCheck(
            "reproducible_calculation", bool(records),
            f"{len(records)} reproducible calculation(s) recorded" if records
            else "no reproducible calculation was recorded",
            evidence={
                "calculations": len(_research_calculations(ctx)),
                "analyses": len(_analysis_records(ctx)),
            },
        ))
        if not records:
            missing.append("no reproducible calculation was recorded")

        return TaskVerification(self.task_type, checks, missing)


class GeneralVerifier:
    """general ⇒ a completed run with a recorded result reference or artifact."""

    task_type = TaskType.GENERAL.value

    def verify(self, ctx: VerificationContext) -> TaskVerification:
        checks: list[VerificationCheck] = []
        missing: list[str] = []

        completed = ctx.status == "completed"
        checks.append(VerificationCheck("run_completed", completed,
                                         "the run finished" if completed else f"the run ended {ctx.status}"))
        if not completed:
            missing.append("the run did not complete")

        state = _observed_state(ctx)
        has_result = bool(ctx.output_reference) or bool(state)
        checks.append(VerificationCheck(
            "result_recorded", has_result,
            "a result reference or an observed record was recorded" if has_result
            else "no result reference or observed record was recorded",
            evidence={"observed": list(state)},
        ))
        if not has_result:
            missing.append("no result reference or observed record was recorded")
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
    WorkflowVerifier(), FinanceVerifier(), DataVerifier(), GeneralVerifier(),
):
    register_verifier(_verifier)


__all__ = [
    "CHECK_CLASSES",
    "CodeVerifier",
    "DataVerifier",
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
