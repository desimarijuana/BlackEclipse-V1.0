"""Research & evidence nodes.

These are LOCAL reads over the existing `EvidenceStore` (the web research
engine's durable evidence graph): evidence, claims, citations, conflicts and a
deterministic report. They do not perform web search and do not call a model;
network research nodes belong to the agent/runtime integration phase.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_ITEMS = 1_000

_store: Any = None


def set_evidence_store(store: Any) -> None:
    global _store
    _store = store


def _require_store() -> Any:
    if _store is None:
        raise ValueError("the evidence store is not configured in this runtime")
    return _store


def _research_id(context: NodeExecContext) -> str:
    value = context.inputs.get("researchId") or context.config.get("researchId") or ""
    research_id = str(value).strip()
    if not research_id:
        raise ValueError("researchId is required: wire it in or set the node's researchId")
    return research_id


def _limit(context: NodeExecContext) -> int:
    try:
        value = int(context.config.get("limit", 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be a whole number") from exc
    return max(1, min(value, MAX_ITEMS))


def _matches(evidence: dict[str, Any], query: str) -> bool:
    if not query:
        return True
    haystack = " ".join([
        str(evidence.get("claimText") or ""),
        str(evidence.get("rawText") or ""),
        str(evidence.get("sourceUrl") or ""),
        json.dumps(evidence.get("structuredValue"), sort_keys=True, default=str),
    ]).lower()
    return query.lower() in haystack


def exec_evidence(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    query = str(context.config.get("query") or "").strip()
    rows = [row for row in store.list_evidence(research_id) if _matches(row, query)]
    rows = rows[: _limit(context)]
    context.emit(f"{len(rows)} evidence item(s) for {research_id}")
    return {
        "evidence": rows,
        "summary": {
            "researchId": research_id,
            "query": query,
            "count": len(rows),
        },
    }


def exec_citations(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    citations = store.list_citations(research_id)[: _limit(context)]
    claims = store.list_claims(research_id)[: _limit(context)]
    return {"citations": citations, "claims": claims}


def exec_conflicts(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    conflicts = store.list_conflicts(research_id)[: _limit(context)]
    return {"conflicts": conflicts}


def _summary(store: Any, research_id: str) -> dict[str, Any]:
    evidence = store.list_evidence(research_id)
    claims = store.list_claims(research_id)
    citations = store.list_citations(research_id)
    conflicts = store.list_conflicts(research_id)
    questions = store.list_questions(research_id)
    supported = [
        claim for claim in claims
        if str(claim.get("status") or "").upper() in ("SUPPORTED", "VERIFIED")
    ]
    unresolved = [
        conflict for conflict in conflicts
        if str(conflict.get("status") or "").upper() not in ("RESOLVED", "DISMISSED")
    ]
    required = [question for question in questions if question.get("required")]
    answered = [question for question in required if question.get("answered")]
    coverage = (len(answered) / len(required)) if required else (1.0 if evidence else 0.0)
    claim_support = (len(supported) / len(claims)) if claims else 0.0
    if not evidence:
        status = "EMPTY"
    elif unresolved or (claims and len(supported) < len(claims)) or coverage < 1:
        status = "PARTIAL"
    else:
        status = "COMPLETE"
    return {
        "researchId": research_id,
        "status": status,
        "evidence": len(evidence),
        "claims": len(claims),
        "supportedClaims": len(supported),
        "claimSupport": round(claim_support, 4),
        "citations": len(citations),
        "conflicts": len(conflicts),
        "unresolvedConflicts": len(unresolved),
        "questions": len(questions),
        "answeredQuestions": len(answered),
        "questionCoverage": round(coverage, 4),
    }


def exec_completeness(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    summary = _summary(store, _research_id(context))
    return {"summary": summary}


def exec_report(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    run = store.get_run(research_id)
    if run is None:
        raise ValueError(f"research run {research_id!r} was not found")
    summary = _summary(store, research_id)
    claims = store.list_claims(research_id)[:20]
    citations = store.list_citations(research_id)[:20]
    conflicts = store.list_conflicts(research_id)[:20]
    evidence = store.list_evidence(research_id)[:20]

    lines = [
        f"# {run.get('question') or research_id}",
        "",
        str(run.get("answer") or "_No synthesized answer was recorded._"),
        "",
        f"_Evidence: {summary['evidence']} · Claims: {summary['claims']} · "
        f"Citations: {summary['citations']} · Conflicts: {summary['unresolvedConflicts']} unresolved_",
        "",
    ]
    if claims:
        lines.append("## Claims")
        for claim in claims:
            lines.append(
                f"- [{claim.get('status') or 'UNKNOWN'}] {claim.get('text') or ''} "
                f"(confidence {claim.get('confidence')})"
            )
        lines.append("")
    if citations:
        lines.append("## Citations")
        for citation in citations:
            title = citation.get("title") or citation.get("sourceUrl") or "source"
            locator = citation.get("locator") or citation.get("section") or ""
            page = f" p.{citation['page']}" if citation.get("page") else ""
            lines.append(f"- {title} — {citation.get('sourceUrl') or ''}{page} {locator}".rstrip())
        lines.append("")
    if conflicts:
        lines.append("## Conflicts")
        for conflict in conflicts:
            lines.append(
                f"- [{conflict.get('status') or 'UNKNOWN'}] "
                f"{conflict.get('metric') or 'metric'} {conflict.get('period') or ''}: "
                f"{conflict.get('explanation') or ''}"
            )
        lines.append("")
    if evidence:
        lines.append("## Evidence")
        for item in evidence:
            text = item.get("claimText") or item.get("rawText") or ""
            lines.append(f"- {str(text)[:400]} ({item.get('sourceUrl') or 'source'})")
    report = "\n".join(lines).strip() + "\n"
    return {"report": report, "summary": summary}


def _research_input() -> tuple[PortDef, ...]:
    return (PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),)


def build_research_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.evidence", version="1.0.0", label="Retrieve evidence",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("query", "string", "", max_length=500),
                ConfigField("limit", "integer", 100, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_evidence,
            metadata={"docs": "Local evidence read; supports an optional text filter."},
        ),
        NodeDef(
            type="research.citations", version="1.0.0", label="Citations & claims",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="citations", name="Citations", type=PortType.ARRAY),
                PortDef(id="claims", name="Claims", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("limit", "integer", 100, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_citations,
        ),
        NodeDef(
            type="research.conflicts", version="1.0.0", label="Conflicts",
            category="research",
            inputs=_research_input(),
            outputs=(PortDef(id="conflicts", name="Conflicts", type=PortType.ARRAY),),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("limit", "integer", 100, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_conflicts,
        ),
        NodeDef(
            type="research.completeness", version="1.0.0", label="Completeness check",
            category="research",
            inputs=_research_input(),
            outputs=(PortDef(id="summary", name="Summary", type=PortType.OBJECT),),
            config_fields=(ConfigField("researchId", "string", "", max_length=200),),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_completeness,
        ),
        NodeDef(
            type="research.report", version="1.0.0", label="Research report",
            category="research",
            inputs=_research_input(),
            outputs=(
                PortDef(id="report", name="Report", type=PortType.STRING),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(ConfigField("researchId", "string", "", max_length=200),),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_report,
            metadata={"docs": "Deterministic Markdown from the stored answer, claims, citations, conflicts and evidence."},
        ),
    ]


__all__ = [
    "build_research_nodes",
    "set_evidence_store",
    "exec_evidence",
    "exec_citations",
    "exec_conflicts",
    "exec_completeness",
    "exec_report",
]
