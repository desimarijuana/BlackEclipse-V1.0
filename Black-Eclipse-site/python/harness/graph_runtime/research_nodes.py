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
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urljoin, urlsplit

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
        str(evidence.get("rawText") or "")[:20_000],
        str(evidence.get("sourceUrl") or ""),
        json.dumps(evidence.get("structuredValue"), sort_keys=True, default=str)[:20_000],
    ]).lower()
    return query.lower() in haystack


# Legacy conflict rows predate the engine's two-status vocabulary. Normalize at
# the READ boundary so every node (and the report) speaks the same language as
# `web_verify.detect_conflicts`.
_CONFLICT_STATUS = {
    "OPEN": "UNRESOLVED",
    "UNRESOLVED": "UNRESOLVED",
    "MATERIAL": "UNRESOLVED",
    "RESOLVED": "RESOLVED",
    "DISMISSED": "RESOLVED",
    "EXPLAINED": "EXPLAINED",
    "NON_MATERIAL": "EXPLAINED",
}


def _conflict_status(value: Any) -> str:
    return _CONFLICT_STATUS.get(str(value or "").strip().upper(), "UNRESOLVED")


def _conflict_rows(store: Any, research_id: str) -> list[dict[str, Any]]:
    """Read conflicts with a normalized status and a decoded candidate list."""
    rows: list[dict[str, Any]] = []
    for row in store.list_conflicts(research_id):
        data = dict(row)
        data["status"] = _conflict_status(data.get("status"))
        data["material"] = bool(data.get("material", True))
        candidates = data.get("candidates")
        if isinstance(candidates, str):
            try:
                candidates = json.loads(candidates)
            except (TypeError, ValueError):
                candidates = []
        data["candidates"] = candidates if isinstance(candidates, list) else []
        rows.append(data)
    return rows


def exec_evidence(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    query = str(context.config.get("query") or "").strip()
    matched = [row for row in store.list_evidence(research_id) if _matches(row, query)]
    rows = matched[: _limit(context)]
    context.emit(f"{len(rows)}/{len(matched)} evidence item(s) for {research_id}")
    return {
        "evidence": rows,
        "summary": {
            "researchId": research_id,
            "query": query,
            "count": len(rows),
            "total": len(matched),
            "truncated": len(rows) < len(matched),
            "status": "EMPTY" if not matched else "OK",
        },
    }


def exec_citations(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    limit = _limit(context)
    all_citations = store.list_citations(research_id)
    all_claims = store.list_claims(research_id)
    return {
        "citations": all_citations[:limit],
        "claims": all_claims[:limit],
        "summary": {
            "researchId": research_id,
            "citations": len(all_citations),
            "claims": len(all_claims),
            "returned": len(all_citations[:limit]) + len(all_claims[:limit]),
            "truncated": len(all_citations) > limit or len(all_claims) > limit,
            "status": "OK",
        },
    }


def exec_conflicts(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    rows = _conflict_rows(store, research_id)
    limit = _limit(context)
    unresolved = [row for row in rows if row["status"] == "UNRESOLVED" and row["material"]]
    return {
        "conflicts": rows[:limit],
        "summary": {
            "researchId": research_id,
            "count": len(rows[:limit]),
            "total": len(rows),
            "unresolved": len(unresolved),
            "truncated": len(rows) > limit,
            "status": "OK",
        },
    }


def _gaps(
    store: Any,
    research_id: str,
    *,
    include_optional: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """What is still missing, in the same terms the engine uses.

    A gap is a named, actionable absence — never a guessed value. `question`
    gaps come from the mandate's required questions; `claim` gaps are claims the
    verifier rejected; `citation` gaps are supported material claims with no
    citation row. With no run data at all there is one `evidence` gap.
    """
    questions = store.list_questions(research_id)
    claims = store.list_claims(research_id)
    citations = store.list_citations(research_id)
    evidence = store.list_evidence(research_id)
    gaps: list[dict[str, Any]] = []

    if not evidence and not claims and not questions:
        gaps.append({
            "kind": "evidence",
            "reason": "no evidence has been recorded for this research run",
        })

    for question in questions:
        if question.get("answered"):
            continue
        if not question.get("required") and not include_optional:
            continue
        gaps.append({
            "kind": "question",
            "id": question.get("id"),
            "text": question.get("question"),
            "intent": question.get("intent"),
            "reason": "required question is unanswered" if question.get("required")
            else "optional question is unanswered",
        })

    cited_claims = {
        str(row.get("claimId")) for row in citations if row.get("claimId")
    }
    for claim in claims:
        status = str(claim.get("status") or "").upper()
        if status in ("UNSUPPORTED", "CONTRADICTED", "OUTDATED"):
            gaps.append({
                "kind": "claim",
                "id": claim.get("id"),
                "text": claim.get("text"),
                "status": status,
                "reason": f"claim is {status.lower()}",
            })
        elif (
            str(claim.get("kind") or "FACT").upper() in ("FACT", "CALCULATION")
            and claim.get("id")
            and str(claim.get("id")) not in cited_claims
            and status not in ("CALCULATED",)
        ):
            gaps.append({
                "kind": "citation",
                "id": claim.get("id"),
                "text": claim.get("text"),
                "reason": "material claim has no citation",
            })
    return gaps[:limit]


def _summary(store: Any, research_id: str) -> dict[str, Any]:
    evidence = store.list_evidence(research_id)
    claims = store.list_claims(research_id)
    citations = store.list_citations(research_id)
    conflicts = _conflict_rows(store, research_id)
    questions = store.list_questions(research_id)
    supported = [
        claim for claim in claims
        if str(claim.get("status") or "").upper() in ("SUPPORTED", "VERIFIED")
    ]
    unresolved = [
        conflict for conflict in conflicts
        if conflict["status"] == "UNRESOLVED" and conflict["material"]
    ]
    required = [question for question in questions if question.get("required")]
    answered = [question for question in required if question.get("answered")]
    if required:
        coverage = len(answered) / len(required)
    else:
        # With no mandate questions, coverage is what the graph can actually
        # prove: claims supported by evidence. No evidence/no claims is 0, not 1.
        coverage = 0.0 if not evidence else ((len(supported) / len(claims)) if claims else 0.0)
    claim_support = (len(supported) / len(claims)) if claims else 0.0
    cited = {str(row.get("claimId")) for row in citations if row.get("claimId")}
    uncited = [
        claim for claim in claims
        if str(claim.get("kind") or "FACT").upper() in ("FACT", "CALCULATION")
        and str(claim.get("id") or "") not in cited
    ]
    gaps = _gaps(store, research_id)
    if not evidence:
        status = "EMPTY"
        verdict = "INSUFFICIENT"
    elif unresolved or (claims and len(supported) < len(claims)) or coverage < 1:
        status = "PARTIAL"
        verdict = "PARTIAL"
    elif not claims:
        status = "PARTIAL"
        verdict = "INSUFFICIENT"
    else:
        status = "COMPLETE"
        verdict = "COMPLETE"
    return {
        "researchId": research_id,
        "status": status,
        "verdict": verdict,
        "evidence": len(evidence),
        "claims": len(claims),
        "supportedClaims": len(supported),
        "claimSupport": round(claim_support, 4),
        "citations": len(citations),
        "uncitedClaims": len(uncited),
        "conflicts": len(conflicts),
        "unresolvedConflicts": len(unresolved),
        "questions": len(questions),
        "answeredQuestions": len(answered),
        "questionCoverage": round(coverage, 4),
        "gaps": gaps,
    }


def exec_completeness(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    summary = _summary(store, research_id)
    summary["runRow"] = store.get_run(research_id) is not None
    return {"summary": summary}


def _md_text(value: Any) -> str:
    """Neutralize raw HTML in untrusted page/claim text; keep the Markdown."""
    return str(value or "").replace("<", "&lt;").replace(">", "&gt;")


def exec_report(context: NodeExecContext) -> dict[str, Any]:
    store = _require_store()
    research_id = _research_id(context)
    try:
        max_items = int(context.config.get("maxItems", 50))
    except (TypeError, ValueError) as exc:
        raise ValueError("maxItems must be a whole number") from exc
    max_items = max(1, min(max_items, MAX_ITEMS))
    run = store.get_run(research_id)
    run_row = run is not None
    summary = _summary(store, research_id)
    claims = store.list_claims(research_id)[:max_items]
    citations = store.list_citations(research_id)[:max_items]
    conflicts = _conflict_rows(store, research_id)[:max_items]
    evidence = store.list_evidence(research_id)[:max_items]
    sources = store.list_sources(research_id)[:max_items]

    question = (run or {}).get("question") or research_id
    answer = (run or {}).get("answer")
    lines = [
        f"# {_md_text(question)}",
        "",
        _md_text(answer) if answer else "UNAVAILABLE — no synthesized answer was recorded.",
        "",
        f"_Evidence: {summary['evidence']} · Claims: {summary['claims']} · "
        f"Citations: {summary['citations']} · "
        f"Conflicts: {summary['unresolvedConflicts']} unresolved · "
        f"Verdict: {summary['verdict']}_",
        "",
    ]
    if claims:
        lines.append("## Claims")
        for claim in claims:
            lines.append(
                f"- [{claim.get('status') or 'UNKNOWN'}] {_md_text(claim.get('text'))} "
                f"(confidence {claim.get('confidence')})"
            )
        lines.append("")
    if citations:
        lines.append("## Citations")
        for index, citation in enumerate(citations, start=1):
            title = _md_text(citation.get("title") or citation.get("sourceUrl") or "source")
            locator = _md_text(citation.get("locator") or citation.get("section") or "")
            page = f" p.{citation['page']}" if citation.get("page") else ""
            lines.append(f"- [{index}] {title} — {_md_text(citation.get('sourceUrl') or '')}{page} {locator}".rstrip())
        lines.append("")
    if conflicts:
        lines.append("## Conflicts")
        for conflict in conflicts:
            lines.append(
                f"- [{conflict.get('status') or 'UNKNOWN'}] "
                f"{_md_text(conflict.get('metric') or 'metric')} "
                f"{_md_text(conflict.get('period') or '')}: "
                f"{_md_text(conflict.get('explanation') or '')}"
            )
        lines.append("")
    gaps = summary.get("gaps") or []
    if gaps:
        lines.append("## Gaps")
        for gap in gaps[:max_items]:
            label = gap.get("text") or gap.get("reason") or gap.get("kind")
            lines.append(f"- [{gap.get('kind')}] {_md_text(label)} — {_md_text(gap.get('reason'))}")
        lines.append("")
    if sources:
        lines.append("## Sources")
        for source in sources:
            title = _md_text(source.get("publisher") or source.get("canonicalUrl") or "source")
            published = f" · published {source['publishedAt']}" if source.get("publishedAt") else ""
            lines.append(f"- {title} — {_md_text(source.get('canonicalUrl') or '')}{published}")
        lines.append("")
    if evidence:
        lines.append("## Evidence")
        for item in evidence:
            text = item.get("claimText") or item.get("rawText") or ""
            lines.append(f"- {_md_text(str(text)[:400])} ({_md_text(item.get('sourceUrl') or 'source')})")
    report = "\n".join(lines).strip() + "\n"
    return {"report": report, "summary": {**summary, "runRow": run_row}}


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
    provider = str(context.config.get("provider") or "").strip()
    research_id = str(
        context.inputs.get("researchId") or context.config.get("researchId") or ""
    ).strip()
    save_sources = bool(context.config.get("saveSources", False)) and bool(research_id)
    store = _require_store() if save_sources else None

    registry = build_default_registry(_bridge_for(context))
    # Ask for more than `limit`, then filter and dedupe. Filtering AFTER the
    # provider's limit silently returned fewer results than the operator asked
    # for whenever a domain filter was set.
    request_limit = min(MAX_SEARCH_RESULTS, max(limit, limit * 3))
    response = _run_async(registry.search(
        query, kind="web", limit=request_limit,
        preference=provider or None,
    ))
    results = []
    seen: set[str] = set()
    saved = 0
    for result in response.results:
        domain = str(getattr(result, "domain", "") or "").lower()
        if include and not any(domain.endswith(d) for d in (d.lower() for d in include)):
            continue
        if exclude and any(domain.endswith(d) for d in (d.lower() for d in exclude)):
            continue
        url = str(getattr(result, "url", "") or "").strip()
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        payload = result.model_dump()
        results.append(payload)
        if save_sources and store is not None and url:
            try:
                from ..research.web_sources import make_source  # noqa: PLC0415

                source = make_source(
                    url,
                    title=payload.get("title"),
                ).model_dump()
                store.save_source(source, research_id=research_id)
                saved += 1
            except Exception:  # noqa: BLE001 - saving a pointer must not fail the search
                saved = saved
        if len(results) >= limit:
            break
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
            "requested": limit,
            "providerResults": len(response.results),
            "filtered": len(response.results) - len(results),
            "truncated": len(results) < len(response.results),
            "domains": include,
            "excludeDomains": exclude,
            "providerPreference": provider or None,
            "savedSources": saved,
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


def _page_links(context: NodeExecContext, url: str) -> tuple[list[str], bool]:
    """Links from ONE page through the bridge's deterministic collector.

    Returns `(links, ok)`. `ok` is False when the collector was unavailable, so
    a caller can distinguish "no links on this page" from "discovery failed".
    """
    try:
        payload = _run_async(_bridge_for(context).fetch("web_collect", {
            "url": url, "selector": "a", "attribute": "href", "maxRows": 50,
        }))
    except Exception:  # noqa: BLE001 - link discovery is best-effort
        return [], False
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return [], False
    links: list[str] = []
    for row in rows:
        value = row.get("href") if isinstance(row, dict) else row
        if not isinstance(value, str) or not value.strip():
            continue
        absolute = urljoin(url, value.strip())
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            continue
        links.append(absolute.split("#", 1)[0])
    return links, True


def exec_web_crawl(context: NodeExecContext) -> dict[str, Any]:
    """A BOUNDED same-site crawl: one start page, at most `maxPages` fetches.

    It reuses the existing SSRF-hardened fetch and the deterministic link
    collector; it is not a general crawler. Every page is untrusted data.
    """
    from ..research.web_extract import fetch  # noqa: PLC0415

    start = str(context.inputs.get("url") or context.config.get("url") or "").strip()
    if not start:
        raise ValueError("url is required: wire it in or set the node's url")
    max_pages = _bounded_int(
        context.config.get("maxPages"), name="maxPages",
        default=5, low=1, high=10,
    )
    max_chars = _bounded_int(
        context.config.get("maxChars"), name="maxChars",
        default=4_000, low=500, high=MAX_FETCH_CHARS,
    )
    same_domain = bool(context.config.get("sameDomain", True))
    max_depth = _bounded_int(
        context.config.get("maxDepth"), name="maxDepth", default=2, low=0, high=2,
    )
    delay_ms = _bounded_int(
        context.config.get("delayMs"), name="delayMs", default=0, low=0, high=2_000,
    )
    start_host = (urlsplit(start).hostname or "").lower()
    if not start_host:
        raise ValueError("url must be an absolute http(s) URL")
    bridge = _bridge_for(context)
    queue: list[tuple[str, int]] = [(start, 0)]
    seen: set[str] = {start}
    pages: list[dict[str, Any]] = []
    failures = 0
    link_failures = 0

    while queue and len(pages) < max_pages:
        current, depth = queue.pop(0)
        result = _run_async(fetch(current, bridge=bridge))
        if not result.ok or not result.text:
            failures += 1
            pages.append({
                "url": current, "status": result.status,
                "error": result.error or "empty content", "title": result.title,
            })
            continue
        links, link_ok = _page_links(context, result.url)
        if not link_ok:
            link_failures += 1
        allowed: list[str] = []
        if depth < max_depth:
            for link in links:
                host = (urlsplit(link).hostname or "").lower()
                if not host or (same_domain and host != start_host):
                    continue
                if link in seen:
                    continue
                seen.add(link)
                allowed.append(link)
                if len(seen) >= max_pages * 5:
                    break
        queue.extend((link, depth + 1) for link in allowed[: max_pages * 2])
        pages.append({
            "url": result.url,
            "title": result.title,
            "status": "OK",
            "depth": depth,
            "text": result.text[:max_chars],
            "truncated": len(result.text) > max_chars,
            "contentHash": result.contentHash,
            "linkDiscovery": "ok" if link_ok else "failed",
            "links": allowed[:20],
        })
        if delay_ms and queue and len(pages) < max_pages:
            import time  # noqa: PLC0415

            time.sleep(delay_ms / 1000.0)

    fetched = [page for page in pages if page.get("status") == "OK"]
    if not fetched:
        raise ValueError(
            f"crawl from {start} fetched no page; this is an unavailable site, "
            "not evidence that the content is absent"
        )
    context.emit(f"crawled {len(fetched)}/{len(pages)} page(s) from {start}")
    return {
        "pages": pages,
        "summary": {
            "startUrl": start,
            "sameDomain": same_domain,
            "requestedPages": max_pages,
            "maxDepth": max_depth,
            "delayMs": delay_ms,
            "fetched": len(fetched),
            "failed": failures,
            "linkDiscoveryFailed": link_failures,
            "status": "OK" if failures == 0 else "PARTIAL",
        },
    }


def exec_claim_verify(context: NodeExecContext) -> dict[str, Any]:
    """Verify ONE claim against stored evidence with the existing verifier."""
    from ..research.web_contracts import Claim, Evidence, SourceConflict  # noqa: PLC0415
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
        # Fall back to the links the run already recorded for this exact claim
        # text. This is the same relationship the engine persisted; nothing is
        # inferred from prose alone.
        wanted = text.strip().lower()
        match = next(
            (row for row in store.list_claims(research_id)
             if str(row.get("text") or "").strip().lower() == wanted),
            None,
        )
        if match is not None and match.get("id"):
            evidence_ids = [
                str(row.get("evidenceId"))
                for row in store.list_claim_evidence(str(match["id"]))
                if row.get("evidenceId")
            ]
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
    conflicts = [SourceConflict(**row) for row in _conflict_rows(store, research_id)]
    claim = verify_claim(
        Claim(text=text, evidenceIds=evidence_ids),
        {eid: Evidence(**rows[eid]) for eid in evidence_ids},
        conflicts=conflicts,
        as_of=str(context.config.get("asOf") or "") or None,
        freshness=str(context.config.get("freshness") or "") or None,
    )
    context.emit(f"claim status {claim.status} (confidence {claim.confidence})")
    return {
        "claim": claim.model_dump(),
        "supported": claim.status in ("SUPPORTED", "CALCULATED"),
        "status": claim.status,
    }


def _research_input() -> tuple[PortDef, ...]:
    return (PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),)


# ── Evidence ranking (pure, no store) ────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _evidence_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("evidence", "items", "rows"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        if raw.get("evidenceId") or raw.get("claimText"):
            return [raw]
    return []


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(float(value), 1.0))


_AUTHORITY_SIGNAL = {
    "official_filing": (1.0, "primary filing"),
    "government": (1.0, "government source"),
    "regulator": (1.0, "regulator source"),
    "investor_relations": (0.9, "investor-relations source"),
    "company": (0.7, "company source"),
    "financial_data": (0.7, "financial-data source"),
    "academic": (0.7, "academic source"),
    "news": (0.5, "news source"),
    "industry": (0.5, "industry source"),
    "analyst": (0.5, "analyst source"),
    "documentation": (0.5, "documentation source"),
    "blog": (0.2, "blog source"),
    "social": (0.1, "social source"),
    "forum": (0.1, "forum source"),
    "wiki": (0.2, "wiki source"),
}


def _authority_for(source_type: Any) -> tuple[Optional[float], Optional[str]]:
    """The recorded source-type authority signal, or no signal at all.

    Only a type the item ALREADY carries is scored. An item with an unknown or
    missing `sourceType` gets no authority component — never a guessed one.
    """
    value = str(source_type or "").strip().lower()
    return _AUTHORITY_SIGNAL.get(value, (None, None))


def _age_days(iso: Any, now: datetime) -> Optional[float]:
    if not isinstance(iso, str) or not iso.strip():
        return None
    text = iso.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (now - parsed).total_seconds() / 86_400.0)


def exec_source_rank(context: NodeExecContext) -> dict[str, Any]:
    """Rank evidence by the signals the items ALREADY carry.

    Two components, both declared: `confidence` (0-1, as recorded upstream) and
    `freshness` (an exponential decay of the published/retrieved date with a
    configurable half-life). An item with neither has NO score — it is sorted
    last and counted as `insufficient_signal`, never given an invented value.
    """
    items = _evidence_items(context.inputs.get("evidence"))
    if not items:
        raise ValueError(
            "research.source_rank needs evidence items (wire an evidence array)"
        )
    try:
        half_life = int(context.config.get("halfLifeDays", 30))
    except (TypeError, ValueError) as exc:
        raise ValueError("Half-life must be a whole number of days") from exc
    half_life = max(1, min(half_life, 3_650))
    now = _now()

    ranking: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        confidence = _number(item.get("confidence"))
        age = _age_days(item.get("publishedAt") or item.get("retrievedAt"), now)
        freshness = None if age is None else round(0.5 ** (age / half_life), 4)
        authority, authority_label = _authority_for(item.get("sourceType"))
        components = [
            value for value in (confidence, freshness, authority) if value is not None
        ]
        score = round(sum(components) / len(components), 4) if components else None
        reasons: list[str] = []
        if confidence is not None:
            reasons.append(f"confidence {confidence:.2f}")
        if age is not None:
            reasons.append(f"published {age:.1f}d ago")
        if authority is not None:
            reasons.append(f"{authority_label} authority {authority:.2f}")
        if score is None:
            reasons.append("no confidence or date recorded")
        ranking.append({
            "index": index,
            "score": score,
            "confidence": confidence,
            "freshness": freshness,
            "authority": authority,
            "ageDays": None if age is None else round(age, 2),
            "reasons": reasons,
        })

    order = sorted(
        range(len(items)),
        key=lambda i: (ranking[i]["score"] is None, -(ranking[i]["score"] or 0.0), i),
    )
    ranked = [{**ranking[i], "rank": position + 1} for position, i in enumerate(order)]
    scored = sum(1 for entry in ranking if entry["score"] is not None)
    context.emit(f"ranked {len(items)} evidence item(s); {scored} with signals")
    return {
        "evidence": [items[i] for i in order],
        "ranking": ranked,
        "summary": {
            "count": len(items),
            "scored": scored,
            "insufficient": len(items) - scored,
            "halfLifeDays": half_life,
        },
    }


def build_research_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.source_rank", version="1.0.0", label="Rank evidence",
            category="research",
            inputs=(PortDef(id="evidence", name="Evidence", type=PortType.ARRAY, optional=True),),
            outputs=(
                PortDef(id="evidence", name="Ranked evidence", type=PortType.ARRAY),
                PortDef(id="ranking", name="Ranking", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("halfLifeDays", "integer", 30, minimum=1, maximum=3_650),
            ),
            capabilities=(),
            side_effects=SideEffect.NONE,
            allowed_modes=_ALL,
            executor=exec_source_rank,
            metadata={
                "docs": (
                    "Pure ranking over the signals the items already carry: "
                    "`confidence` and `freshness` (exponential decay of "
                    "publishedAt/retrievedAt with a configurable half-life). An item "
                    "with neither is sorted last and reported as insufficient_signal "
                    "— no score is invented."
                ),
            },
        ),
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
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
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
            outputs=(
                PortDef(id="conflicts", name="Conflicts", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
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
            config_fields=(
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("maxItems", "integer", 50, minimum=1, maximum=MAX_ITEMS),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_report,
            metadata={"docs": "Deterministic Markdown from the stored answer, claims, citations, conflicts, gaps, sources and evidence. A missing run row yields an UNAVAILABLE answer, not an error."},
        ),
        NodeDef(
            type="research.web_search", version="1.0.0", label="Web search",
            category="research",
            inputs=(
                PortDef(id="query", name="Query", type=PortType.STRING, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="results", name="Results", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("query", "string", "", max_length=500),
                ConfigField("limit", "integer", 8, minimum=1, maximum=MAX_SEARCH_RESULTS),
                ConfigField("domains", "array", []),
                ConfigField("excludeDomains", "array", []),
                ConfigField("provider", "string", "", max_length=80),
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("saveSources", "boolean", False),
            ),
            capabilities=("network.egress", "research.read", "research.write"),
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
            type="research.web_crawl", version="1.0.0", label="Crawl site",
            category="research",
            inputs=(PortDef(id="url", name="URL", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="pages", name="Pages", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("url", "string", "", max_length=2_000),
                ConfigField("maxPages", "integer", 5, minimum=1, maximum=10),
                ConfigField("maxChars", "integer", 4_000, minimum=500, maximum=MAX_FETCH_CHARS),
                ConfigField("sameDomain", "boolean", True),
                ConfigField("maxDepth", "integer", 2, minimum=0, maximum=2),
                ConfigField("delayMs", "integer", 0, minimum=0, maximum=2_000),
            ),
            capabilities=("network.egress",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=240_000,
            executor=exec_web_crawl,
            metadata={
                "docs": (
                    "Bounded same-site crawl through the SSRF-hardened bridge and its "
                    "deterministic link collector. Not a general crawler; text is untrusted."
                ),
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
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            executor=exec_claim_verify,
            metadata={"docs": "Local claim verification against stored evidence (no model call). Conflicts and point-in-time rules are applied; with no evidence ids it uses the run's recorded claim links."},
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
    "exec_web_crawl",
    "exec_claim_verify",
]
