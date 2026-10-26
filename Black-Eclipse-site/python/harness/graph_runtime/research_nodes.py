"""Research & evidence nodes.

Two families:

- LOCAL reads over the existing `EvidenceStore` (the web research engine's
  durable evidence graph): evidence, claims, citations, conflicts, a
  deterministic report and claim verification. No web request, no model call.
- NETWORK nodes over the SAME web-research engine: `research.web_search` calls
  the configured search provider chain and `research.web_fetch` fetches one page
  through the SSRF-hardened bridge. Both are declared `network` side effects, so
  the compiler only allows them in an explicitly authorized operator run.

Nothing here re-implements search, fetching or verification: the engine modules
(`web_providers`, `web_extract`, `web_verify`) own those decisions.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)
MAX_ITEMS = 1_000
MAX_SEARCH_RESULTS = 15
MAX_FETCH_CHARS = 100_000
DEFAULT_FETCH_CHARS = 8_000
MAX_CLAIM_CHARS = 4_000

_store: Any = None
_bridge: Any = None


def set_evidence_store(store: Any) -> None:
    global _store
    _store = store


def set_research_bridge(bridge: Any) -> None:
    """Bind a data bridge for tests/embeddings; a real run resolves one from the
    node context's callback URL instead."""
    global _bridge
    _bridge = bridge


def _bridge_for(context: NodeExecContext) -> Any:
    if _bridge is not None:
        return _bridge
    from ..bridge import HttpDataBridge  # noqa: PLC0415

    base_url = context.callback_base_url.strip()
    if not base_url:
        raise ValueError(
            "web research needs the data bridge; this run has no callback URL. "
            "Start it as an operator run from the app."
        )
    return HttpDataBridge(base_url, context.callback_token)


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


def _run_async(coro: Any) -> Any:
    import asyncio  # noqa: PLC0415

    return asyncio.run(coro)


def _bounded_int(raw: Any, *, name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw if raw is not None else default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a whole number") from exc
    if value < low or value > high:
        raise ValueError(f"{name} must be between {low} and {high}")
    return value


def _string_list(raw: Any, *, name: str) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(part).strip() for part in raw if str(part).strip()]
    raise ValueError(f"{name} must be an array of strings")


def exec_web_search(context: NodeExecContext) -> dict[str, Any]:
    """Search the web through the existing provider chain.

    Results are POINTERS (title/url/snippet), never evidence. An unavailable
    route is reported honestly, never as an empty success.
    """
    from ..research.web_providers import build_default_registry  # noqa: PLC0415

    query = str(context.inputs.get("query") or context.config.get("query") or "").strip()
    if not query:
        raise ValueError("query is required: wire it in or set the node's query")
    limit = _bounded_int(
        context.config.get("limit"), name="limit",
        default=8, low=1, high=MAX_SEARCH_RESULTS,
    )
    include = _string_list(context.config.get("domains"), name="domains")
    exclude = _string_list(context.config.get("excludeDomains"), name="excludeDomains")

    registry = build_default_registry(_bridge_for(context))
    response = _run_async(registry.search(query, kind="web", limit=limit))
    results = []
    for result in response.results:
        domain = str(getattr(result, "domain", "") or "").lower()
        if include and not any(domain.endswith(d) for d in (d.lower() for d in include)):
            continue
        if exclude and any(domain.endswith(d) for d in (d.lower() for d in exclude)):
            continue
        results.append(result.model_dump())
    context.emit(
        f"{len(results)} result(s) for {query!r} via {response.provider or 'search'}"
    )
    return {
        "results": results,
        "summary": {
            "query": query,
            "status": response.status,
            "provider": response.provider,
            "count": len(results),
            "domains": include,
            "excludeDomains": exclude,
            "diagnostics": response.diagnostics,
            "error": response.error,
            "note": "Search results are pointers, not evidence; fetch a page before citing it.",
        },
    }


def exec_web_fetch(context: NodeExecContext) -> dict[str, Any]:
    """Fetch ONE page through the SSRF-hardened bridge and return its text.

    The extracted text is untrusted page data. When `researchId` is set, the
    same `Evidence` the web tools store is saved to the EvidenceStore, so the
    local research nodes can read it afterwards.
    """
    from ..research.web_extract import fetch, fetch_to_evidence  # noqa: PLC0415
    from ..research.web_sources import make_source  # noqa: PLC0415

    url = str(context.inputs.get("url") or context.config.get("url") or "").strip()
    if not url:
        raise ValueError("url is required: wire it in or set the node's url")
    max_chars = _bounded_int(
        context.config.get("maxChars"), name="maxChars",
        default=DEFAULT_FETCH_CHARS, low=500, high=MAX_FETCH_CHARS,
    )
    research_id = str(
        context.inputs.get("researchId") or context.config.get("researchId") or ""
    ).strip()
    store = _require_store() if research_id else None
    result = _run_async(fetch(url, bridge=_bridge_for(context)))
    escalation: Optional[str] = None
    if bool(context.config.get("allowBrowser", False)):
        from ..research.web_browser import browser_extract, needs_escalation  # noqa: PLC0415
        from ..research.web_extract import FetchResult, content_hash  # noqa: PLC0415

        escalate, reason = needs_escalation(
            text=result.text, fetch_status=result.status, fetch_error=result.error,
        )
        if escalate:
            outcome = _run_async(browser_extract(result.url or url))
            if outcome.ok:
                result = FetchResult(
                    ok=True, url=outcome.url or url, text=outcome.text,
                    title=outcome.title, status="OK", extraction="browser",
                    contentHash=content_hash(outcome.text),
                )
                escalation = reason
            else:
                escalation = f"browser escalation unavailable: {outcome.reason}"
    if not result.ok or not result.text:
        raise ValueError(
            f"could not retrieve {url}: {result.error or 'empty content'}"
            + (f" ({escalation})" if escalation else "")
            + "; this is an unavailable source, not evidence that the content is absent"
        )

    truncated = len(result.text) > max_chars
    text = result.text[:max_chars]
    evidence = fetch_to_evidence(result)
    if research_id and evidence is not None and store is not None:
        evidence_payload = evidence.model_dump()
        evidence_payload["rawText"] = text
        store.save_source(
            make_source(result.url, title=result.title).model_dump(),
            research_id=research_id,
        )
        store.save_evidence(evidence_payload, research_id=research_id)

    context.emit(f"fetched {len(result.text)} chars from {result.url}")
    page = {
        "url": result.url,
        "title": result.title,
        "status": "OK",
        "contentHash": result.contentHash,
        "characters": len(result.text),
        "truncated": truncated,
        "extraction": result.extraction,
        "escalation": escalation,
        "researchId": research_id or None,
        "evidence": evidence.model_dump() if evidence is not None else None,
    }
    return {"text": text, "page": page}


def exec_claim_verify(context: NodeExecContext) -> dict[str, Any]:
    """Verify ONE claim against stored evidence with the existing verifier."""
    from ..research.web_contracts import Claim, Evidence  # noqa: PLC0415
    from ..research.web_verify import verify_claim  # noqa: PLC0415

    store = _require_store()
    research_id = _research_id(context)
    text = str(context.inputs.get("claim") or context.config.get("claim") or "").strip()
    if not text:
        raise ValueError("claim is required: wire it in or set the node's claim")
    if len(text) > MAX_CLAIM_CHARS:
        raise ValueError(f"claim exceeds {MAX_CLAIM_CHARS} characters")
    evidence_ids = _string_list(
        context.inputs.get("evidenceIds")
        if context.inputs.get("evidenceIds") is not None
        else context.config.get("evidenceIds"),
        name="evidenceIds",
    )
    if not evidence_ids:
        raise ValueError("evidenceIds is required: name at least one evidence id")

    rows = {
        row["evidenceId"]: row
        for row in store.list_evidence(research_id)
        if row.get("evidenceId")
    }
    missing = [eid for eid in evidence_ids if eid not in rows]
    if missing:
        raise ValueError(f"unknown evidence id(s) for {research_id}: {', '.join(missing)}")
    claim = verify_claim(
        Claim(text=text, evidenceIds=evidence_ids),
        {eid: Evidence(**rows[eid]) for eid in evidence_ids},
    )
    context.emit(f"claim status {claim.status} (confidence {claim.confidence})")
    return {
        "claim": claim.model_dump(),
        "supported": claim.status == "SUPPORTED",
        "status": claim.status,
    }


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
        NodeDef(
            type="research.web_search", version="1.0.0", label="Web search",
            category="research",
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="results", name="Results", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("query", "string", "", max_length=500),
                ConfigField("limit", "integer", 8, minimum=1, maximum=MAX_SEARCH_RESULTS),
                ConfigField("domains", "array", []),
                ConfigField("excludeDomains", "array", []),
            ),
            capabilities=("network.egress",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=20_000,
            executor=exec_web_search,
            metadata={
                "docs": "Search through the configured provider chain. Results are pointers; "
                        "requires an explicit network grant.",
            },
        ),
        NodeDef(
            type="research.web_fetch", version="1.0.0", label="Fetch page",
            category="research",
            inputs=(
                PortDef(id="url", name="URL", type=PortType.STRING, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="text", name="Text", type=PortType.STRING),
                PortDef(id="page", name="Page", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("url", "string", "", max_length=2_000),
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("maxChars", "integer", DEFAULT_FETCH_CHARS, minimum=500, maximum=MAX_FETCH_CHARS),
                ConfigField("allowBrowser", "boolean", False),
            ),
            capabilities=("network.egress",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=30_000,
            executor=exec_web_fetch,
            metadata={
                "docs": "SSRF-hardened fetch through the bridge; text is untrusted. With a "
                        "research id the evidence is saved for the local research nodes.",
            },
        ),
        NodeDef(
            type="research.claim_verify", version="1.0.0", label="Verify claim",
            category="research",
            inputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
                PortDef(id="claim", name="Claim", type=PortType.STRING, optional=True),
                PortDef(id="evidenceIds", name="Evidence ids", type=PortType.ARRAY, optional=True),
            ),
            outputs=(
                PortDef(id="claim", name="Claim", type=PortType.OBJECT),
                PortDef(id="supported", name="Supported", type=PortType.BOOLEAN),
                PortDef(id="status", name="Status", type=PortType.STRING),
            ),
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("claim", "string", "", max_length=MAX_CLAIM_CHARS),
                ConfigField("evidenceIds", "array", []),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_claim_verify,
            metadata={"docs": "Local claim verification against stored evidence (no model call)."},
        ),
    ]


__all__ = [
    "build_research_nodes",
    "set_evidence_store",
    "set_research_bridge",
    "exec_evidence",
    "exec_citations",
    "exec_conflicts",
    "exec_completeness",
    "exec_report",
    "exec_web_search",
    "exec_web_fetch",
    "exec_claim_verify",
]
