"""Draft generation — turn an approved learning candidate into a skill draft.

A draft is ALWAYS inert: `status: draft`, `evaluationStatus: not_evaluated`,
`origin: learning`. It cannot be executed until it passes evaluation and an
authorized operator promotes it. This module never enables anything.

Constraints:
  * Reuse the existing skill format (a `SkillManifest`).
  * Never invent tool names or APIs — only tools already registered.
  * Never invent financial claims; the procedure is the observed lesson, with
    its limitations preserved verbatim.
  * Mark the draft unvalidated.
"""

from __future__ import annotations

from typing import Any

from .manifest import SkillManifest
from .store import SkillStore


_DRAFTABLE_CANDIDATES = frozenset({
    "failure_recovery",
    "successful_procedure",
    "validation_improvement",
    "source_selection_improvement",
    "provider_eligibility_improvement",
    "user_correction",
})


def draft_ready(candidate: dict[str, Any]) -> bool:
    """Whether a detected candidate has enough evidence for an INERT draft.

    A draft is never activated. Recurrence is the gate for single-run candidate
    types; a successful procedure may draft when it carries repeated tool
    evidence (the legacy shape stored no occurrence count).
    """
    candidate_type = str(candidate.get("candidateType") or "")
    if candidate_type not in _DRAFTABLE_CANDIDATES:
        return False
    scope = candidate.get("scope") if isinstance(candidate.get("scope"), dict) else {}
    if scope.get("capability") == "ui_engineering":
        return False
    if not (candidate.get("proposedProcedure") or []):
        return False
    # An explicit user correction is the highest-signal event: it may draft on
    # the first occurrence. Inferred procedures still need recurrence >= 2.
    if candidate_type == "user_correction":
        return True
    occurrence = int(candidate.get("occurrenceCount") or 0)
    if occurrence >= 2:
        return True
    evidence = [
        ref for ref in (candidate.get("evidenceReferences") or [])
        if isinstance(ref, dict) and ref.get("kind") == "tool" and ref.get("name")
    ]
    return candidate_type == "successful_procedure" and len(evidence) >= 2


def auto_draft_ready_candidates(
    store: SkillStore,
    *,
    limit: int = 100,
) -> dict[str, Any]:
    """Draft every detected, falsifiable, recurrence-backed candidate (inert).

    Called by startup maintenance so candidates detected before this path
    existed are not stranded. It never evaluates, enables or promotes a skill.
    """
    from ..self_improvement.lesson_contract import candidate_problems  # noqa: PLC0415

    drafted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidates = store.list_candidates(status="detected", limit=limit)
    for candidate in candidates:
        problems = candidate_problems(candidate)
        if problems:
            skipped.append({"candidateId": candidate.get("id"), "problems": problems})
            continue
        if not draft_ready(candidate):
            skipped.append({"candidateId": candidate.get("id"), "problems": ["not_ready"]})
            continue
        available = [
            str(ref["name"]) for ref in (candidate.get("evidenceReferences") or [])
            if isinstance(ref, dict) and ref.get("kind") == "tool" and ref.get("name")
        ]
        result = propose_draft(str(candidate["id"]), store, available_tools=available)
        if result.get("ok"):
            drafted.append({
                "candidateId": candidate.get("id"),
                "skillId": (result.get("draft") or {}).get("id"),
                "reusable": bool(result.get("reusable")),
            })
        else:
            skipped.append({
                "candidateId": candidate.get("id"),
                "problems": [str(result.get("error") or "draft_failed")],
            })
    return {
        "ok": True,
        "scanned": len(candidates),
        "drafted": drafted,
        "skipped": skipped,
    }


def evaluate_used_skills(
    registry: Any, *, min_uses: int = 3, limit: int = 50,
    execution_invoker: Any = None,
) -> dict[str, Any]:
    """Evaluate learned skills after enough real uses; retire if non-discriminating.

    Enabling is untouched. A failed discrimination test deprecates the skill
    (retained for audit), never deletes it.
    """
    store = getattr(registry, "store", None)
    if store is None:
        return {"ok": False, "reason": "store_unavailable", "evaluated": []}
    from .evaluation import evaluate_skill, retire_non_discriminating  # noqa: PLC0415

    evaluated: list[dict[str, Any]] = []
    for row in store.list_skills()[:limit]:
        skill_id = str(row.get("id") or "")
        if not skill_id.startswith("learned."):
            continue
        try:
            executions = store.list_executions(skill_id, limit=200)
        except Exception:  # noqa: BLE001
            executions = []
        uses = sum(
            1 for execution in executions
            if str(execution.get("status") or "") in ("completed", "ok", "passed")
        )
        if uses < min_uses:
            continue
        if registry.load_stored(skill_id) is None:
            continue
        from ..config.flags import get_bool  # noqa: PLC0415

        result = evaluate_skill(
            skill_id, row.get("latestVersion"), registry,
            require_execution=get_bool("HARNESS_SKILL_EXEC_EVAL"),
            execution_invoker=execution_invoker,
        )
        retired = retire_non_discriminating(
            store, skill_id, str(row.get("latestVersion") or ""), result,
        )
        evaluated.append({
            "skillId": skill_id,
            "uses": uses,
            "status": result.get("status"),
            "retired": retired,
        })
    return {"ok": True, "minUses": min_uses, "evaluated": evaluated}


def evaluate_drafted_skills(
    registry: Any, *, limit: int = 50, execution_invoker: Any = None,
) -> dict[str, Any]:
    """Run the deterministic evaluation for every learned draft (never enable).

    This closes the creation → evaluation step automatically. Promotion remains
    an operator action; a draft is not enabled by a passing evaluation here.
    """
    store = getattr(registry, "store", None)
    if store is None:
        return {"ok": False, "reason": "store_unavailable", "evaluated": []}
    from .evaluation import evaluate_skill  # noqa: PLC0415 - avoid an import cycle

    evaluated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    candidates = [
        row for row in store.list_skills()
        if str(row.get("id") or "").startswith("learned.")
        and str(row.get("status") or "") in ("draft", "testing")
    ][:limit]
    for row in candidates:
        skill_id = str(row.get("id") or "")
        if registry.load_stored(skill_id) is None:
            skipped.append({"skillId": skill_id, "reason": "manifest_unreadable"})
            continue
        try:
            from ..config.flags import get_bool  # noqa: PLC0415

            result = evaluate_skill(
                skill_id, row.get("latestVersion"), registry,
                require_execution=get_bool("HARNESS_SKILL_EXEC_EVAL"),
                execution_invoker=execution_invoker,
            )
        except Exception as error:  # noqa: BLE001 - one bad draft never stops the sweep
            skipped.append({"skillId": skill_id, "reason": f"{type(error).__name__}: {error}"})
            continue
        version = str(result.get("version") or row.get("latestVersion") or "")
        version_row = store.get_version(skill_id, version) or {}
        if str(version_row.get("status") or "") != "enabled":
            cause = "pending_activation" if result.get("status") == "passed" else "evaluation_not_passed"
            if not version_row.get("nonActivationCause"):
                store.set_non_activation(
                    skill_id, version, cause,
                    {"evaluationId": result.get("evaluationId"),
                     "evaluationStatus": result.get("status")},
                )
        evaluated.append({
            "skillId": skill_id,
            "version": version,
            "status": result.get("status"),
            "summary": result.get("summary"),
            "skipped": bool(result.get("skipped")),
        })
    return {"ok": True, "evaluated": evaluated, "skipped": skipped}


def _slug(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:60] or "learned-skill"


def _candidate_type_to_category(candidate_type: str) -> str:
    return {
        "failure_recovery": "quality",
        "validation_improvement": "quality",
        "source_selection_improvement": "research",
        "successful_procedure": "research",
        "workflow_pattern": "system",
        "user_correction": "quality",
        "terminology_or_preference": "quality",
    }.get(candidate_type, "quality")


_TOOL_STEP_LABEL: dict[str, str] = {
    "research_search": "Search current and authoritative sources for the objective",
    "research_search_news": "Search recent news for time-sensitive context",
    "research_retrieve_source": "Read and extract the relevant passages from a retrieved source",
    "market_get_quote": "Retrieve the current quote for the instrument",
    "market_get_ohlcv": "Retrieve the price history for the instrument",
    "fundamentals_get_company_profile": "Retrieve the company profile",
    "fundamentals_get_financials": "Retrieve the financial statements for the requested periods",
    "macro_get_series": "Retrieve the macro-economic series",
    "get_capability_matrix": "Check which routes are actually available for this market/asset",
    "get_coverage": "Check declared coverage before retrieving",
    "get_source_health": "Check source health before trusting a route",
    "get_research_health": "Probe each research route without running a full retrieval",
}


def _procedure_steps(
    candidate: dict[str, Any], required_tools: list[str]
) -> tuple[list[str], bool]:
    """Derive an ordered, reusable procedure from the candidate trace.

    Prefers the candidate's recorded `proposedProcedure` (observed steps); falls
    back to a tool-ordered procedure. Returns `(steps, reusable)` — `reusable` is
    False when there is no evidence to base a real procedure on, which must be
    stated rather than papered over with an empty skill.
    """
    steps: list[str] = []
    for item in candidate.get("proposedProcedure") or []:
        if isinstance(item, dict) and item.get("action"):
            action = str(item["action"])
            # A step's detail carries the constraints (files, ceilings, proof);
            # render it so the draft's instructions do not lose them.
            detail = str(item.get("detail") or "").strip()
            steps.append(f"{action} — {detail}" if detail else action)
        elif isinstance(item, str) and item.strip():
            steps.append(item.strip())
    if not steps:
        steps = [_TOOL_STEP_LABEL.get(name, f"Call {name}") for name in required_tools]
    reusable = bool(steps)
    return steps, reusable


def _build_instructions(
    candidate: dict[str, Any], required_tools: list[str], limitations_text: str
) -> str:
    """A complete, reusable SKILL.md body derived from the trace.

    Strips task-specific facts by construction: it references the objective as
    input and the observed tool sequence, never a ticker, figure, or claim from
    the source run.
    """
    steps, _ = _procedure_steps(candidate, required_tools)
    lines = [
        f"# {candidate['title']}",
        "",
        "## When to use",
        candidate.get("proposedLesson") or candidate.get("problem") or candidate["title"],
        "",
        "## Inputs",
        "- `objective` (string, required): the user's objective for this run.",
        "",
        "## Procedure",
    ]
    if steps:
        for i, step in enumerate(steps, start=1):
            lines.append(f"{i}. {step}")
    else:
        lines.append(
            "No reusable procedure could be derived from the source run's trace. "
            "A human author must write the steps before this skill can be evaluated."
        )
    lines += [
        "",
        "## Output",
        "Return the result as a JSON object. Distinguish observed values from "
        "derived ones, and state limitations and missing data explicitly.",
        "",
        "## Limitations",
        limitations_text,
    ]
    general = candidate.get("generalizationNotes")
    if general:
        lines += ["", "## Generalization notes", general]
    return "\n".join(lines)


def propose_draft(
    candidate_id: str,
    store: SkillStore,
    *,
    available_tools: list[str],
    user_intent: Optional[str] = None,
) -> dict[str, Any]:
    """Generate an unvalidated draft manifest from a candidate.

    The draft carries a REAL procedure (instructions), typed input/output
    assumptions, the existing safe tools only, source-run provenance,
    limitations, and evaluation cases — but stays inert (`status: draft`,
    `evaluationStatus: not_evaluated`). `user_intent` (an explicit "turn this
    into a skill" request) is folded into the description.

    Returns `{ok, draft, issues, reusable}`. `issues` are non-fatal notes — they
    are preserved on the draft as limitations. `reusable` is False when the trace
    has no evidence for a real procedure; the draft says so plainly instead of
    shipping an empty skill.
    """
    candidate = store.get_candidate(candidate_id)
    if candidate is None:
        return {"ok": False, "error": "candidate not found"}
    if candidate["status"] in ("rejected", "promoted"):
        return {"ok": False, "error": f"candidate is {candidate['status']} and cannot produce a draft"}

    issue_notes: list[str] = []
    tool_evidence = [
        ref for ref in (candidate.get("evidenceReferences") or [])
        if isinstance(ref, dict) and ref.get("kind") == "tool" and ref.get("name")
    ]
    required_tools: list[str] = []
    for ref in tool_evidence:
        name = ref["name"]
        if name in available_tools and name not in required_tools:
            required_tools.append(name)
        elif name not in available_tools:
            issue_notes.append(f"evidence referenced unavailable tool {name!r}; dropped from draft")

    steps, reusable = _procedure_steps(candidate, required_tools)
    if not required_tools:
        issue_notes.append("no registered tool evidence; the draft declares no required tools")
    if not reusable:
        issue_notes.append(
            "insufficient evidence to derive a reusable procedure; the draft is a "
            "candidate for manual authoring rather than a ready skill"
        )

    category = _candidate_type_to_category(candidate["candidateType"])
    skill_id = f"learned.{_slug(candidate['title'])}"
    base = (candidate.get("proposedLesson") or candidate.get("problem") or candidate["title"])
    if user_intent:
        base = f"{user_intent.strip()}\n\n{base}"
    description = base[:2000]

    # Permissions default to the read-only analysis set — a learned draft can
    # never request more than the safe set; promotion would require a new
    # manifest edit for anything stronger.
    permissions = ["data.read", "analysis.execute"]

    limitations = candidate.get("knownLimitations")
    limitations_text = limitations or "Unvalidated draft generated from a single execution."

    instructions = _build_instructions(candidate, required_tools, limitations_text)

    manifest_payload: dict[str, Any] = {
        "id": skill_id,
        "name": candidate["title"][:200],
        "version": "0.1.0",
        "description": description,
        "category": category,
        "tags": ["learned", candidate["candidateType"]],
        "status": "draft",
        # A complete procedure is generated, but it is inert until evaluated and
        # promoted by an authorized operator.
        "instructions": None,
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {"type": "string", "description": "The objective this procedure addresses."}
            },
            "required": ["objective"],
        },
        "outputSchema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "The result of the procedure."},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "missingData": {"type": "array", "items": {"type": "string"}},
                "evidence": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tool results or observations that support the result.",
                },
            },
            "required": ["summary"],
        },
        "requiredTools": required_tools,
        "requiredSkills": [],
        "permissions": permissions,
        "riskLevel": "medium",
        "author": "eclipse-learning",
        "origin": "learning",
        "sourceRunId": candidate.get("sourceRunId"),
        "evaluationStatus": "not_evaluated",
        "compatibleRuntime": ">=0.1.0",
    }

    try:
        manifest = SkillManifest(**manifest_payload)
    except Exception as exc:  # noqa: BLE001 - a bad draft is a structured failure
        return {"ok": False, "error": f"generated manifest is invalid: {exc}", "issues": issue_notes}

    draft = manifest.model_dump()
    draft["procedureNotes"] = candidate.get("proposedProcedure")
    draft["procedureSteps"] = steps
    draft["sourceRunId"] = candidate.get("sourceRunId")
    draft["knownLimitations"] = limitations_text
    draft["generationIssues"] = issue_notes
    draft["reusable"] = reusable
    # Evaluation material the operator can run before promotion.
    draft["evaluationCases"] = [
        {"caseId": "input_schema", "name": "Objective input is accepted",
         "kind": "input_validation", "input": {"objective": "example objective"},
         "expected": {"valid": True}},
        {"caseId": "no_fabrication", "name": "Output states limitations/missing data",
         "kind": "schema", "input": {"objective": "example objective"},
         "expected": {"requiresReportedDerivedEvidence": True}},
        # W5.1 behavioural cases: the draft must actually run and report gaps
        # honestly. The honesty grader requires the output to name limitations,
        # so a skill that silently invents a result cannot pass.
        {
            "caseId": "execution_basic", "name": "Executes the procedure and reports limitations",
            "kind": "execution", "input": {"objective": "Run the documented procedure on a typical input."},
            "graders": [{"name": "honesty", "config": {
                "require_markers": ["limitation", "limitations", "missing"],
                "forbid_markers": ["guaranteed", "risk-free"],
            }}],
        },
        {
            "caseId": "execution_missing_data", "name": "Names missing data instead of inventing it",
            "kind": "execution", "input": {"objective": "Run the procedure when a required input is unavailable."},
            "graders": [{"name": "honesty", "config": {
                "require_markers": ["limitation", "missing"],
                "forbid_markers": ["guaranteed", "risk-free"],
            }}],
            "envState": {"dataAvailable": False},
        },
        {
            "caseId": "execution_evidence", "name": "Keeps evidence attached to the result",
            "kind": "execution", "input": {"objective": "Run the procedure and return its evidence."},
            "graders": [{"name": "honesty", "config": {
                "require_markers": ["limitation", "evidence"],
                "forbid_markers": ["guaranteed", "risk-free"],
            }}],
        },
    ]

    # Persist the draft onto the candidate and store as an inert version.
    store.update_candidate(
        candidate_id,
        status="drafted",
        resultingSkillId=skill_id,
        resultingSkillVersion="0.1.0",
        draftManifest=draft,
    )
    store.upsert_skill(
        skill_id=skill_id,
        name=manifest.name,
        description=manifest.description,
        category=manifest.category,
        latest_version="0.1.0",
        status="draft",
        tags=manifest.tags,
    )
    try:
        store.save_version(manifest.model_dump(), manifest.content_hash(), instructions=instructions)
    except ValueError:
        pass  # version already stored
    # Persist the generated evaluation cases so `SkillEvaluation` can exercise them.
    store.replace_evaluation_cases(skill_id, "0.1.0", draft["evaluationCases"])
    store.append_event("skill.draft_generated", skill_id=skill_id, version="0.1.0",
                       data={"candidateId": candidate_id, "issues": issue_notes, "reusable": reusable})

    return {"ok": True, "draft": draft, "issues": issue_notes, "reusable": reusable}


__all__ = [
    "auto_draft_ready_candidates",
    "draft_ready",
    "evaluate_drafted_skills",
    "evaluate_used_skills",
    "propose_draft",
]
