"""The Quant Research Dossier.

One durable document that binds the question, the literature, the method
specifications, the comparison, the reproduction, the validation and the
limitations. It computes nothing of its own: every number comes from the
reproduction record, and every paper comes from the literature table.

A dossier without a reproduction or validation is still useful, but it is marked
`partial` and says what is missing.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Iterable

from ..errors import QuantError
from .suitability import compare_methods
from .visuals import build_research_figures, figures_markdown


def _ids(values: Iterable[str] | None) -> list[str]:
    out: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _method_view(record: dict[str, Any]) -> dict[str, Any]:
    spec = record.get("spec") or {}
    return {
        "methodId": spec.get("methodId") or record.get("id"),
        "name": spec.get("name") or record.get("name"),
        "family": spec.get("family") or record.get("methodFamily"),
        "version": spec.get("version"),
        "objective": spec.get("objective") or [],
        "inputs": spec.get("inputs") or [],
        "equations": spec.get("equations") or [],
        "assumptions": spec.get("assumptions") or [],
        "limitations": spec.get("limitations") or [],
        "implementationStatus": spec.get("implementationStatus"),
        "reproductionStatus": spec.get("reproductionStatus"),
        "lifecycleStatus": spec.get("lifecycleStatus"),
        "references": spec.get("references") or [],
        "provenance": spec.get("provenance") or {},
    }


def _render_markdown(dossier: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# {dossier['title']}",
        "",
        f"**Status:** {dossier['status']}  ",
        f"**Method schema:** {dossier.get('schemaVersion', '1.0.0')}  ",
        f"**Dossier id:** {dossier.get('dossierId', 'pending')}",
        "",
        "## Research question",
        "",
        dossier.get("researchQuestion") or "Not stated.",
        "",
        "## Scope",
        "",
        f"- Instrument: {dossier.get('scope', {}).get('instrument') or 'not stated'}",
        f"- Timeframe: {dossier.get('scope', {}).get('timeframe') or 'not stated'}",
        f"- Objective: {dossier.get('scope', {}).get('objective') or 'not stated'}",
        "",
        "## Literature review",
        "",
    ]
    literature = dossier.get("literature") or []
    if literature:
        for item in literature:
            year = f" ({item.get('year')})" if item.get("year") else ""
            venue = f" — {item['venue']}" if item.get("venue") else ""
            url = f" — {item['url']}" if item.get("url") else ""
            lines.append(f"- {item.get('title')}{year}{venue}{url}")
    else:
        lines.append("No literature was reviewed. This is a gap, not evidence of novelty.")

    lines.extend(["", "## Established methods", ""])
    methods = dossier.get("methods") or []
    if methods:
        for method in methods:
            lines.append(f"### {method.get('name')} (`{method.get('methodId')}`)")
            lines.append("")
            lines.append(f"- Family: {method.get('family')}")
            lines.append(f"- Lifecycle: {method.get('lifecycleStatus')}")
            lines.append(f"- Implementation: {method.get('implementationStatus')}")
            lines.append(f"- Reproduction: {method.get('reproductionStatus')}")
            if method.get("objective"):
                lines.append(f"- Objective: {', '.join(method['objective'])}")
            if method.get("assumptions"):
                lines.append("- Assumptions:")
                lines.extend(f"  - {a}" for a in method["assumptions"])
            lines.append("")
    else:
        lines.append("No method specification was selected.")

    lines.extend(["", "## Mathematical comparison", ""])
    if methods:
        for method in methods:
            lines.append(f"### {method.get('name')}")
            for eq in method.get("equations") or []:
                lines.append("")
                lines.append("```latex")
                lines.append(str(eq.get("latex") or ""))
                lines.append("```")
                source = eq.get("source") or {}
                where = source.get("literatureId") or source.get("citation") or "source not recorded"
                page = f", p. {source['page']}" if source.get("page") else ""
                section = f", §{source['section']}" if source.get("section") else ""
                lines.append(f"_Source: {where}{section}{page}_")
    else:
        lines.append("No equations were available to compare.")

    lines.extend(["", "## Suitability assessment", ""])
    comparison = dossier.get("suitability") or []
    if comparison:
        lines.append("| Method | Fit | Caveat |")
        lines.append("|---|---:|---|")
        for row in comparison:
            caveat = "; ".join(row.get("warnings") or []) or "—"
            lines.append(f"| {row.get('name')} | {row.get('score')}/100 | {caveat} |")
        lines.append("")
        lines.append("A fit score is methodological suitability, not a probability of profit.")
    else:
        lines.append("No suitability comparison was computed.")

    lines.extend(["", "## Data requirements", ""])
    requirements: list[str] = []
    for method in methods:
        for item in method.get("inputs") or []:
            if item.get("name"):
                requirements.append(f"- {item['name']} ({item.get('frequency', 'frequency not stated')})")
    lines.extend(requirements or ["No data requirement was recorded."])

    lines.extend(["", "## Reproduction", ""])
    reproductions = dossier.get("reproductions") or []
    if reproductions:
        for rep in reproductions:
            lines.append(f"### {rep.get('methodId')} — `{rep.get('id')}`")
            lines.append("")
            lines.append(f"- Status: {rep.get('status')}")
            observed = rep.get("observedMetrics") or {}
            if observed:
                lines.append("- Observed metrics:")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(observed, indent=2, sort_keys=True, default=str))
                lines.append("```")
            fidelity = rep.get("fidelity") or {}
            if fidelity:
                lines.append(f"- Fidelity: {fidelity.get('note') or json.dumps(fidelity, default=str)}")
            lines.append("")
    else:
        lines.append("No reproduction was run. A specification is not a reproduction.")

    lines.extend(["", "## Validation", ""])
    validations = dossier.get("validations") or []
    if validations:
        for validation in validations:
            lines.append(f"### `{validation.get('reproductionId')}` — {validation.get('status')}")
            lines.append("")
            for check in validation.get("checks") or []:
                lines.append(f"- **{check.get('check')}**: {check.get('status')} — {check.get('detail')}")
            lines.append("")
    else:
        lines.append("No validation was run.")

    lines.extend(["", "## Limitations", ""])
    limitations = dossier.get("limitations") or []
    lines.extend(f"- {item}" for item in limitations) if limitations else lines.append(
        "No limitation was recorded. That is itself a limitation."
    )

    lines.extend(["", "## Figures", ""])
    blocks = dossier.get("figures") or []
    if blocks:
        lines.append("These figures are computed from the data and experiments in this dossier.")
        lines.append("")
        lines.append(figures_markdown(blocks))
    else:
        lines.append("No research figure was available. A missing input is not a reason to draw an empty chart.")

    lines.extend(["", "## Reproducibility", ""])
    lines.append(f"- Content hash: {dossier.get('contentHash') or 'not recorded'}")
    lines.append(f"- Session: {dossier.get('sessionId') or 'not linked'}")
    lines.append(f"- Research run: {dossier.get('researchId') or 'not linked'}")
    lines.append("- Every number above came from a deterministic Eclipse run; no "
                 "value was computed by the language model.")

    lines.extend(["", "## References", ""])
    references = dossier.get("references") or []
    if references:
        lines.extend(f"- {ref}" for ref in references)
    else:
        lines.append("No reference was recorded.")

    lines.extend([
        "",
        "---",
        "",
        "A method card is not evidence. A reproduction is not a trading edge. "
        "A backtest is not a promise. This dossier states what was measured and "
        "what was not.",
        "",
    ])
    return "\n".join(lines)


def build_dossier(
    store: Any,
    *,
    title: str,
    question: str,
    artifact_service: Any = None,
    session_id: str | None = None,
    research_id: str | None = None,
    method_ids: Iterable[str] | None = None,
    literature_ids: Iterable[str] | None = None,
    reproduction_ids: Iterable[str] | None = None,
    constraints: dict[str, Any] | None = None,
    summary: str = "",
    run_id: str | None = None,
    series: list[dict[str, Any]] | None = None,
    symbol: str = "",
) -> dict[str, Any]:
    method_ids = _ids(method_ids)
    literature_ids = _ids(literature_ids)
    reproduction_ids = _ids(reproduction_ids)

    literature: list[dict[str, Any]] = []
    for lit_id in literature_ids:
        try:
            literature.append(store.get_literature(lit_id))
        except QuantError:
            continue
    methods: list[dict[str, Any]] = []
    for method_id in method_ids:
        try:
            methods.append(_method_view(store.get_method_spec(method_id)))
        except QuantError:
            continue

    reproductions: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []
    for rep_id in reproduction_ids:
        try:
            rep = store.get_reproduction(rep_id)
        except QuantError:
            continue
        reproductions.append(rep)
        if rep.get("validation"):
            validations.append(rep["validation"])

    suitability = compare_methods(
        [store.get_method_spec(m)["spec"] for m in method_ids
         if _safe(store, m)] if method_ids else [],
        constraints or {"objective": question},
    )

    figure_result = build_research_figures(
        methods=methods or None,
        comparison=suitability or None,
        series=series,
        symbol=symbol,
        reproduction=reproductions[0] if reproductions else None,
    )

    missing: list[str] = []
    if not literature:
        missing.append("no literature reviewed")
    if not methods:
        missing.append("no method specification selected")
    if not reproductions:
        missing.append("no reproduction run")
    if not validations:
        missing.append("no validation run")
    status = "complete" if not missing else "partial"

    references: list[str] = []
    for item in literature:
        if item.get("title"):
            references.append(
                f"{item['title']} ({item.get('year') or 'n.d.'})"
                + (f" — {item.get('url')}" if item.get("url") else "")
            )
    for method in methods:
        for ref in method.get("references") or []:
            citation = ref.get("citation") if isinstance(ref, dict) else str(ref)
            if citation and citation not in references:
                references.append(citation)

    limitations: list[str] = []
    for method in methods:
        for item in method.get("limitations") or []:
            if item not in limitations:
                limitations.append(item)
    limitations.extend(f"Not measured: {item}." for item in missing)

    dossier = {
        "schemaVersion": "1.0.0",
        "title": title or "Quant research dossier",
        "researchQuestion": question,
        "scope": {
            "instrument": (constraints or {}).get("instrument"),
            "timeframe": (constraints or {}).get("timeframe"),
            "objective": (constraints or {}).get("objective") or question,
        },
        "status": status,
        "sessionId": session_id,
        "researchId": research_id,
        "literature": literature,
        "methods": methods,
        "suitability": suitability,
        "reproductions": reproductions,
        "validations": validations,
        "figures": figure_result["blocks"],
        "figureNotes": figure_result["figures"],
        "figureUnavailable": figure_result["unavailable"],
        "summary": summary,
        "limitations": limitations,
        "missing": missing,
        "references": references,
        "contentHash": None,
    }

    markdown = _render_markdown(dossier)
    import hashlib

    dossier["contentHash"] = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    markdown = _render_markdown(dossier)
    artifact_id = None
    artifact_error = None
    if artifact_service is not None:
        try:
            from ...artifacts.model import ArtifactCategory, ArtifactSourceType

            artifact = artifact_service.register_bytes(
                markdown.encode("utf-8"),
                name=f"{title or 'quant-research'}.md",
                description=question[:400],
                category=ArtifactCategory.REPORT,
                mime_type="text/markdown",
                source_type=ArtifactSourceType.AGENT,
                source_tool="quant_build_dossier",
                tags=["quant", "research", "dossier"],
                run_id=run_id,
                metadata={"researchId": research_id, "sessionId": session_id,
                          "status": status},
            )
            artifact_id = artifact.id
        except Exception as exc:  # noqa: BLE001 - artifact failure must not lose the dossier
            artifact_error = str(exc)

    dossier["dossierId"] = f"dsr_{uuid.uuid4().hex[:16]}"
    saved = store.save_dossier({
        "id": dossier["dossierId"],
        "sessionId": session_id,
        "researchId": research_id,
        "title": dossier["title"],
        "question": question,
        "status": status,
        "artifactId": artifact_id,
        "dossier": {**dossier, "markdown": markdown},
    })
    dossier["dossierId"] = saved["id"]
    dossier["artifactId"] = artifact_id
    if artifact_error:
        dossier["artifactError"] = artifact_error
    return {"dossier": dossier, "dossierId": saved["id"], "artifactId": artifact_id,
            "markdown": markdown, "status": status, "missing": missing}


def _safe(store: Any, method_id: str) -> bool:
    try:
        store.get_method_spec(method_id)
        return True
    except QuantError:
        return False


__all__ = ["build_dossier"]
