"""Research network adapters (Wave B).

Four bounded adapters over the EXISTING web-research engine:

- `research.fetch_many` fetches a known list of URLs through the SSRF-hardened
  bridge (the missing verb between one `web_fetch` and a site `web_crawl`).
- `research.scrape` collects table/record rows through the bridge's
  `web_collect` capability, with no model.
- `research.extract_facts` runs the engine's model-assisted, span-validated fact
  extractor over fetched pages. A model proposal that does not validate is a
  rejection note, never evidence.
- `research.deep_dive` invokes the existing `ResearchEngine` (plan → search →
  fetch → validate → verify → synthesize) and returns its run id.

No new search, fetch or verification path is implemented here. Everything is a
`network` effect (or `model` for pure extraction), so a test run is refused by
the compiler and an operator run must explicitly grant network access.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, Optional
from urllib.parse import urlsplit

from ..research.web_contracts import ResearchDepth, ResearchRequest
from ..research.web_facts import MAX_PAGES, WebFactExtractor, WebPageContent
from ..research.mandate import FactLeg, ResearchMandate
from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext
from .research_nodes import (
    _bridge_for,
    _bounded_int,
    _require_store,
    _research_id,
    _run_async,
    _string_list,
)

_ALL = tuple(ExecutionMode)
MAX_ITEMS = 1_000
MAX_FETCH_URLS = 10
MAX_FETCH_CHARS = 100_000
DEFAULT_FETCH_CHARS = 8_000
DEFAULT_TIERS = ("primary", "official", "structured", "secondary")


def _rows(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("pages", "evidence", "items", "rows", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [raw]
    return []


def _urls(context: NodeExecContext) -> list[str]:
    collected: list[str] = []
    wired = context.inputs.get("urls")
    if isinstance(wired, (list, tuple)):
        for item in wired:
            if isinstance(item, str):
                collected.append(item)
            elif isinstance(item, dict):
                collected.append(str(item.get("url") or item.get("sourceUrl") or ""))
    elif isinstance(wired, dict):
        collected.append(str(wired.get("url") or wired.get("sourceUrl") or ""))
    results = context.inputs.get("results")
    for item in _rows(results) if results is not None else []:
        collected.append(str(item.get("url") or ""))
    configured = context.config.get("urls")
    if isinstance(configured, str):
        try:
            configured = json.loads(configured) if configured.strip().startswith("[") else configured.split(",")
        except (TypeError, ValueError) as exc:
            raise ValueError("urls must be an array of URLs") from exc
    for item in configured or []:
        collected.append(str(item))
    urls: list[str] = []
    seen: set[str] = set()
    for raw in collected:
        url = raw.strip()
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            if url:
                raise ValueError(f"not an absolute http(s) URL: {url!r}")
            continue
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
    if not urls:
        raise ValueError("urls is required: wire search results or set the node's urls")
    if len(urls) > MAX_FETCH_URLS:
        raise ValueError(f"fetch at most {MAX_FETCH_URLS} URLs per node")
    return urls


def exec_fetch_many(context: NodeExecContext) -> dict[str, Any]:
    from ..research.web_extract import fetch, fetch_to_evidence  # noqa: PLC0415
    from ..research.web_sources import make_source  # noqa: PLC0415

    urls = _urls(context)
    max_chars = _bounded_int(
        context.config.get("maxChars"), name="maxChars",
        default=DEFAULT_FETCH_CHARS, low=500, high=MAX_FETCH_CHARS,
    )
    concurrency = _bounded_int(
        context.config.get("concurrency"), name="concurrency",
        default=2, low=1, high=4,
    )
    research_id = str(
        context.inputs.get("researchId") or context.config.get("researchId") or ""
    ).strip()
    save_evidence = bool(context.config.get("saveEvidence", True)) and bool(research_id)
    store = _require_store() if save_evidence else None
    bridge = _bridge_for(context)
    allow_browser = bool(context.config.get("allowBrowser", False))
    dedupe = bool(context.config.get("dedupe", True))

    async def _one(url: str) -> tuple[Any, Optional[str]]:
        result = await fetch(url, bridge=bridge)
        escalation: Optional[str] = None
        if allow_browser:
            from ..research.web_browser import browser_extract, needs_escalation  # noqa: PLC0415
            from ..research.web_extract import FetchResult, content_hash  # noqa: PLC0415

            escalate, reason = needs_escalation(
                text=result.text, fetch_status=result.status, fetch_error=result.error,
            )
            if escalate:
                outcome = await browser_extract(result.url or url)
                if outcome.ok:
                    result = FetchResult(
                        ok=True, url=outcome.url or url, text=outcome.text,
                        title=outcome.title, status="OK", extraction="browser",
                        contentHash=content_hash(outcome.text),
                    )
                    escalation = reason
                else:
                    escalation = f"browser escalation unavailable: {outcome.reason}"
        return result, escalation

    async def _all() -> list[Any]:
        semaphore = asyncio.Semaphore(concurrency)

        async def _guarded(url: str) -> Any:
            async with semaphore:
                return await _one(url)

        return await asyncio.gather(*(_guarded(url) for url in urls))

    outcomes = _run_async(_all())
    pages: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    seen_hashes: dict[str, str] = {}
    fetched = 0
    failed = 0
    deduped = 0
    for url, (result, escalation) in zip(urls, outcomes):
        if not result.ok or not result.text:
            failed += 1
            pages.append({
                "url": result.url or url,
                "status": result.status,
                "error": result.error or "empty content",
                "title": result.title,
                "escalation": escalation,
            })
            continue
        fetched += 1
        content_hash = str(result.contentHash or "")
        duplicate_of = seen_hashes.get(content_hash) if dedupe and content_hash else None
        if duplicate_of:
            deduped += 1
        elif content_hash:
            seen_hashes[content_hash] = result.url or url
        text = result.text[:max_chars]
        evidence = fetch_to_evidence(result)
        evidence_id: Optional[str] = None
        if evidence is not None:
            evidence_id = evidence.evidenceId
            if not duplicate_of:
                evidence_rows.append(evidence.model_dump())
                if save_evidence and store is not None:
                    payload = evidence.model_dump()
                    payload["rawText"] = text
                    store.save_source(
                        make_source(result.url, title=result.title).model_dump(),
                        research_id=research_id,
                    )
                    store.save_evidence(payload, research_id=research_id)
        pages.append({
            "url": result.url or url,
            "title": result.title,
            "status": "OK",
            "contentHash": content_hash or None,
            "characters": len(result.text),
            "truncated": len(result.text) > max_chars,
            "extraction": result.extraction,
            "escalation": escalation,
            "evidenceId": evidence_id,
            "duplicateOf": duplicate_of,
            "text": text,
        })

    if fetched == 0 and failed:
        raise ValueError(
            f"could not retrieve any of {len(urls)} URL(s); this is an unavailable "
            "source set, not evidence that the content is absent"
        )
    status = "OK" if failed == 0 else "PARTIAL"
    context.emit(f"fetched {fetched}/{len(urls)} page(s) ({deduped} duplicate)")
    return {
        "pages": pages,
        "evidence": evidence_rows,
        "summary": {
            "requested": len(urls),
            "fetched": fetched,
            "failed": failed,
            "deduped": deduped,
            "concurrency": concurrency,
            "saved": bool(save_evidence),
            "researchId": research_id or None,
            "status": status,
        },
    }


def exec_scrape(context: NodeExecContext) -> dict[str, Any]:
    url = str(context.inputs.get("url") or context.config.get("url") or "").strip()
    if not url:
        raise ValueError("url is required: wire it in or set the node's url")
    params: dict[str, Any] = {"url": url}
    selector = str(context.config.get("selector") or "").strip()
    attribute = str(context.config.get("attribute") or "").strip()
    fields = context.config.get("fields")
    max_rows = _bounded_int(
        context.config.get("maxRows"), name="maxRows", default=100, low=1, high=200,
    )
    if selector:
        params["selector"] = selector
    if attribute:
        params["attribute"] = attribute
    if fields:
        parsed = fields
        if isinstance(fields, str):
            try:
                parsed = json.loads(fields)
            except (TypeError, ValueError) as exc:
                raise ValueError("fields must be a JSON object or array") from exc
        params["fields"] = parsed
    if bool(context.config.get("tables", False)):
        params["tables"] = True
    params["maxRows"] = max_rows

    payload = _run_async(_bridge_for(context).fetch("web_collect", params))
    if not isinstance(payload, dict):
        raise ValueError("the web collector returned an invalid payload")
    status = str(payload.get("status") or "UNAVAILABLE")
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    page = {
        "url": str(payload.get("finalUrl") or url),
        "status": status,
        "error": payload.get("error"),
        "failureClass": payload.get("failureClass"),
        "contentType": payload.get("contentType"),
        "retrievedAt": payload.get("retrievedAt"),
        "extraction": payload.get("extraction"),
        "columns": payload.get("columns") if isinstance(payload.get("columns"), list) else [],
        "matched": payload.get("matched"),
        "truncated": bool(payload.get("truncated")),
    }
    context.emit(
        f"collected {len(rows)} row(s) and {len(tables)} table(s) from {page['url']} ({status})"
    )
    return {
        "rows": rows[:max_rows],
        "tables": tables[:2],
        "page": page,
        "summary": {
            "rows": min(len(rows), max_rows),
            "tables": min(len(tables), 2),
            "maxRows": max_rows,
            "status": status,
        },
    }


def _model_for(context: NodeExecContext, timeout_s: float) -> Any:
    """A one-shot model adapter for `WebFactExtractor` (no tools, no loop)."""
    if not context.model_settings:
        raise ValueError(
            "model settings are unavailable for this run; start it as an operator "
            "run with a configured model provider"
        )
    try:
        from ..schemas import ModelSettings  # noqa: PLC0415

        settings = ModelSettings(**context.model_settings)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"invalid model settings: {exc}") from exc

    class _RuntimeModel:
        async def ainvoke(self, messages: Any) -> Any:
            from ..model_runtime import get_runtime  # noqa: PLC0415

            response = await get_runtime().generate(
                settings=settings,
                messages=messages,
                task="graph_research_facts",
                timeout_s=timeout_s,
                temperature=0.0,
            )
            return SimpleNamespace(content=getattr(response, "text", "") or "")

    return _RuntimeModel()


def _tier_for(source_type: Any) -> str:
    value = str(source_type or "unknown").strip().lower()
    if value in ("official_filing", "government", "regulator", "investor_relations"):
        return "primary"
    if value in ("financial_data", "academic"):
        return "structured"
    if value in ("company", "news", "industry", "analyst", "blog", "documentation"):
        return "secondary"
    return "unknown"


def exec_extract_facts(context: NodeExecContext) -> dict[str, Any]:
    rows = _rows(context.inputs.get("pages"))
    if not rows:
        raise ValueError("pages is required: wire the output of research.fetch_many")
    objective = str(context.config.get("objective") or "").strip()
    if not objective:
        raise ValueError("objective is required: describe the facts to extract")

    raw_legs = context.config.get("legsJson")
    if isinstance(raw_legs, str):
        try:
            raw_legs = json.loads(raw_legs) if raw_legs.strip() else []
        except (TypeError, ValueError) as exc:
            raise ValueError("legsJson must be a JSON array") from exc
    if not isinstance(raw_legs, list) or not raw_legs:
        raise ValueError("legsJson must declare at least one fact leg")
    legs: list[FactLeg] = []
    for index, item in enumerate(raw_legs[:20]):
        if not isinstance(item, dict) or not str(item.get("metric") or "").strip():
            raise ValueError(f"leg {index + 1} needs a metric")
        legs.append(FactLeg(
            id=str(item.get("id") or f"leg{index + 1}"),
            metric=str(item["metric"]),
            entityRaw=str(item.get("entity") or item.get("entityRaw") or ""),
            entitySymbol=item.get("symbol"),
            period=item.get("period"),
            basis=item.get("basis"),
            unit=item.get("unit"),
            currency=item.get("currency"),
        ))

    permitted = set(_string_list(context.config.get("permittedTiers"), name="permittedTiers"))
    permitted = permitted or set(DEFAULT_TIERS)
    timeout_s = _bounded_int(
        context.config.get("timeoutMs"), name="timeoutMs", default=120_000,
        low=10_000, high=180_000,
    ) / 1000.0

    pages: list[WebPageContent] = []
    skipped: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:MAX_PAGES]):
        text = str(row.get("text") or row.get("rawText") or "")
        url = str(row.get("url") or row.get("sourceUrl") or "")
        if not text.strip() or not url:
            skipped.append({"url": url or None, "reason": "page has no text or url"})
            continue
        pages.append(WebPageContent(
            pageId=str(row.get("evidenceId") or row.get("pageId") or f"p{index + 1}"),
            url=url,
            title=row.get("title"),
            publishedAt=row.get("publishedAt"),
            text=text,
            tier=_tier_for(row.get("sourceType")),  # type: ignore[arg-type]
        ))
    if not pages:
        raise ValueError("no page with usable text was supplied to extract facts from")

    mandate = ResearchMandate(objective=objective, factLegs=legs)
    extractor = WebFactExtractor(_model_for(context, timeout_s), timeout_s=timeout_s)
    accepted, notes = _run_async(
        extractor.extract(mandate, legs, pages, permitted_tiers=set(permitted))
    )
    evidence = [
        item.model_dump() if hasattr(item, "model_dump") else dict(item)
        for item in accepted
    ]
    rejected = list(notes) + skipped
    context.emit(
        f"extracted {len(evidence)} validated fact(s); {len(rejected)} rejected"
    )
    return {
        "evidence": evidence,
        "rejected": rejected,
        "summary": {
            "pages": len(pages),
            "accepted": len(evidence),
            "rejected": len(rejected),
            "legs": len(legs),
            "permittedTiers": sorted(permitted),
            "status": "OK" if evidence else "EMPTY",
        },
    }


def exec_deep_dive(context: NodeExecContext) -> dict[str, Any]:
    from ..research.web_engine import ResearchEngine  # noqa: PLC0415

    question = str(
        context.inputs.get("question") or context.config.get("question") or ""
    ).strip()
    if not question:
        raise ValueError("question is required: wire it in or set the node's question")
    depth = str(context.config.get("depth") or "standard").strip().lower()
    if depth not in {item.value for item in ResearchDepth}:
        raise ValueError(f"depth must be one of {', '.join(item.value for item in ResearchDepth)}")
    request = ResearchRequest(
        question=question,
        depth=ResearchDepth(depth),
        freshness=str(context.config.get("freshness") or "") or None,
        pointInTime=str(context.config.get("asOf") or "") or None,
        minSources=_bounded_int(
            context.config.get("minSources"), name="minSources", default=3, low=1, high=20,
        ),
        maxSources=_bounded_int(
            context.config.get("maxSources"), name="maxSources", default=12, low=1, high=30,
        ),
        maxQueries=_bounded_int(
            context.config.get("maxQueries"), name="maxQueries", default=12, low=1, high=30,
        ),
        maxTimeSeconds=float(_bounded_int(
            context.config.get("maxTimeSeconds"), name="maxTimeSeconds",
            default=300, low=10, high=600,
        )),
        citationsRequired=bool(context.config.get("citationsRequired", True)),
        primarySourcesRequired=bool(context.config.get("primarySourcesRequired", False)),
    )
    engine = ResearchEngine(bridge=_bridge_for(context), store=_require_store())
    result = _run_async(engine.run(request))
    payload = result.to_dict()
    context.emit(
        f"deep dive {result.researchId} finished {payload['status'].get('state')}"
    )
    coverage = payload.get("coverage") or {}
    return {
        "researchId": result.researchId,
        "answer": payload.get("answer") or "",
        "summary": {
            "researchId": result.researchId,
            "state": payload["status"].get("state"),
            "stopReason": payload["status"].get("stopReason"),
            "coverage": coverage.get("status"),
            "sources": len(payload.get("sources") or []),
            "evidence": len(payload.get("evidence") or []),
            "claims": len(payload.get("claims") or []),
            "conflicts": len(payload.get("conflicts") or []),
            "status": payload["status"].get("state"),
        },
    }


def build_research_network_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="research.fetch_many", version="1.0.0", label="Fetch pages",
            category="research",
            inputs=(
                PortDef(id="urls", name="URLs", type=PortType.ARRAY, optional=True),
                PortDef(id="results", name="Search results", type=PortType.ARRAY, optional=True),
                PortDef(id="researchId", name="Research id", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="pages", name="Pages", type=PortType.ARRAY),
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("urls", "array", []),
                ConfigField("researchId", "string", "", max_length=200),
                ConfigField("maxChars", "integer", DEFAULT_FETCH_CHARS, minimum=500, maximum=MAX_FETCH_CHARS),
                ConfigField("allowBrowser", "boolean", False),
                ConfigField("concurrency", "integer", 2, minimum=1, maximum=4),
                ConfigField("dedupe", "boolean", True),
                ConfigField("saveEvidence", "boolean", True),
            ),
            capabilities=("network.egress", "research.read", "research.write"),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_fetch_many,
            metadata={"docs": "Fetches 1-10 known URLs (typically research.web_search results) through the SSRF-hardened bridge. Failed URLs are rows, not exceptions; duplicate content is fetched once; a failed batch is an explicit error."},
        ),
        NodeDef(
            type="research.scrape", version="1.0.0", label="Collect table / records",
            category="research",
            inputs=(PortDef(id="url", name="URL", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="rows", name="Rows", type=PortType.ARRAY),
                PortDef(id="tables", name="Tables", type=PortType.ARRAY),
                PortDef(id="page", name="Page", type=PortType.OBJECT),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("url", "string", "", max_length=2_000),
                ConfigField("selector", "string", "", max_length=200),
                ConfigField("attribute", "string", "", max_length=80),
                ConfigField("fields", "array", []),
                ConfigField("tables", "boolean", False),
                ConfigField("maxRows", "integer", 100, minimum=1, maximum=200),
            ),
            capabilities=("network.egress",),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_scrape,
            metadata={"docs": "Deterministic table/record collection through the bridge's web_collect capability. No model. An unavailable page is a page status, never empty rows presented as success."},
        ),
        NodeDef(
            type="research.extract_facts", version="1.0.0", label="Extract facts",
            category="research",
            inputs=(PortDef(id="pages", name="Pages", type=PortType.ARRAY, optional=True),),
            outputs=(
                PortDef(id="evidence", name="Evidence", type=PortType.ARRAY),
                PortDef(id="rejected", name="Rejected", type=PortType.ARRAY),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("objective", "string", "", max_length=2_000),
                ConfigField("legsJson", "array", []),
                ConfigField("permittedTiers", "array", list(DEFAULT_TIERS)),
                ConfigField("timeoutMs", "integer", 120_000, minimum=10_000, maximum=180_000),
            ),
            capabilities=("agent.run",),
            side_effects=SideEffect.MODEL,
            allowed_modes=_ALL,
            timeout_ms=180_000,
            executor=exec_extract_facts,
            metadata={"docs": "Model-assisted extraction followed by the engine's deterministic span validation. A fact is evidence only when its page, verbatim span, number and metric/period all validate; everything else is a rejection note."},
        ),
        NodeDef(
            type="research.deep_dive", version="1.0.0", label="Run research engine",
            category="research",
            inputs=(PortDef(id="question", name="Question", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="researchId", name="Research id", type=PortType.STRING),
                PortDef(id="answer", name="Answer", type=PortType.STRING),
                PortDef(id="summary", name="Summary", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("question", "string", "", max_length=2_000),
                ConfigField("depth", "string", "standard", max_length=40),
                ConfigField("freshness", "string", "", max_length=40),
                ConfigField("asOf", "string", "", max_length=40),
                ConfigField("minSources", "integer", 3, minimum=1, maximum=20),
                ConfigField("maxSources", "integer", 12, minimum=1, maximum=30),
                ConfigField("maxQueries", "integer", 12, minimum=1, maximum=30),
                ConfigField("maxTimeSeconds", "integer", 300, minimum=10, maximum=600),
                ConfigField("citationsRequired", "boolean", True),
                ConfigField("primarySourcesRequired", "boolean", False),
            ),
            capabilities=("network.egress", "agent.run", "research.read", "research.write"),
            side_effects=SideEffect.NETWORK,
            allowed_modes=_ALL,
            timeout_ms=600_000,
            executor=exec_deep_dive,
            metadata={"docs": "Runs the existing ResearchEngine (the same orchestration as /research/web/*) with its own budget caps and a hard timeout. Returns the run id so the local read nodes can inspect it. Operator-only: it is a network effect."},
        ),
    ]


__all__ = [
    "build_research_network_nodes",
    "exec_fetch_many",
    "exec_scrape",
    "exec_extract_facts",
    "exec_deep_dive",
]
