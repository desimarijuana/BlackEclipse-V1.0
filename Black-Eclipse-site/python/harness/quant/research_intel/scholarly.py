"""Scholarly discovery over the existing research connectors.

Eclipse already owns the provider chain (OpenAlex/Crossref/arXiv and the web
fallback) behind `harness.research`. This module does not open a new transport:
it plans queries, calls that registry, normalizes and deduplicates the answers,
and records them as literature metadata with stable identifiers.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from ..errors import QuantError
from .query_planner import plan_queries

_DOI = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
_ARXIV = re.compile(r"\barxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z.-]+/\d{7})(?:\.pdf)?")
_YEAR = re.compile(r"\b(19|20)\d{2}\b")

_ACADEMIC_SOURCES = {
    "openalex", "crossref", "arxiv", "semantic_scholar", "semanticscholar",
    "ssrn", "nber", "repec", "github", "google_scholar",
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _identifiers(title: str, url: str, snippet: str = "") -> dict[str, str | None]:
    text = f"{url} {snippet} {title}"
    doi = _DOI.search(text)
    arxiv = _ARXIV.search(url or text)
    return {
        "doi": doi.group(0).lower().rstrip(".") if doi else None,
        "arxivId": arxiv.group(1) if arxiv else None,
    }


def _year(text: str) -> int | None:
    found = _YEAR.search(text or "")
    return int(found.group(0)) if found else None


def _normalize(result: Any) -> dict[str, Any]:
    title = str(getattr(result, "title", "") or "").strip()
    url = str(getattr(result, "url", "") or "").strip()
    snippet = str(getattr(result, "snippet", "") or "").strip()
    ids = _identifiers(title, url, snippet)
    published = getattr(result, "publishedAt", None)
    return {
        "title": title,
        "url": url,
        "abstract": snippet or None,
        "authors": [getattr(result, "author")] if getattr(result, "author", None) else [],
        "year": _year(str(published or "")) or _year(snippet) or _year(title),
        "venue": getattr(result, "domain", None),
        "provider": str(getattr(result, "provider", "") or "unknown"),
        "sourceId": str(getattr(result, "resultId", "") or "") or None,
        "accessStatus": "open" if getattr(result, "isOpenAccess", False) or
                        (url and not ids.get("doi")) else "unknown",
        "pdfUrl": getattr(result, "pdfUrl", None),
        "isOpenAccess": bool(getattr(result, "isOpenAccess", False)),
        "references": list(getattr(result, "references", []) or []),
        **ids,
    }


def _dedupe(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for record in records:
        key = (
            f"doi:{_norm(record.get('doi'))}" if record.get("doi")
            else f"arxiv:{_norm(record.get('arxivId'))}" if record.get("arxivId")
            else "title:" + re.sub(r"[^a-z0-9]+", "", _norm(record.get("title")))
        )
        if key in seen:
            # Prefer the richer record, but keep both providers on the survivor.
            prior = seen[key]
            providers = set(prior.get("providers") or [prior.get("provider")])
            providers.add(record.get("provider"))
            prior["providers"] = sorted(p for p in providers if p)
            if len(record.get("abstract") or "") > len(prior.get("abstract") or ""):
                prior["abstract"] = record["abstract"]
            continue
        record["providers"] = [record.get("provider")] if record.get("provider") else []
        seen[key] = record
        out.append(record)
    return out


async def search_literature(
    store: Any,
    bridge: Any,
    *,
    objective: str,
    problem: str = "",
    instrument: str = "",
    timeframe: str = "",
    sources: list[str] | None = None,
    limit: int = 8,
    max_queries: int = 8,
    research_id: str | None = None,
) -> dict[str, Any]:
    """Search the existing scholarly connectors and persist the pointers."""
    from ...research.web_providers import build_default_registry

    plan = plan_queries(
        objective, problem=problem, instrument=instrument, timeframe=timeframe,
        max_queries=max_queries,
    )
    registry = build_default_registry(bridge)
    diagnostics: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []

    for item in plan["queries"]:
        query = item["query"]
        try:
            response = await registry.search(query, kind="academic", limit=limit)
        except Exception as exc:  # noqa: BLE001 - a provider failure is data
            diagnostics.append({"query": query, "provider": "academic",
                                "status": "ERROR", "error": str(exc)})
            continue
        diagnostics.extend(response.diagnostics or [])
        if response.status == "OK" and response.results:
            raw.extend(_normalize(r) for r in response.results)
            continue
        # An honest fallback: scholarly-host web search, still a pointer.
        try:
            fallback = await registry.search(
                f"{query} site:arxiv.org OR site:doi.org OR site:ssrn.com",
                kind="web", limit=limit,
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append({"query": query, "provider": "web",
                                "status": "ERROR", "error": str(exc)})
            continue
        diagnostics.extend(fallback.diagnostics or [])
        if fallback.status == "OK":
            raw.extend(_normalize(r) for r in fallback.results)

    # Repository-scoped discovery. These sources do not expose a clean public
    # API, so Eclipse uses a scoped web query and labels the result a pointer.
    scoped = (
        ("nber", "site:nber.org"),
        ("repec", "site:ideas.repec.org"),
        ("ssrn", "site:ssrn.com"),
    )
    requested_sources = {s.lower() for s in (sources or [])}
    for query in [q["query"] for q in plan["queries"][:2]]:
        for name, scope in scoped:
            if requested_sources and name not in requested_sources:
                continue
            try:
                response = await registry.search(f"{query} {scope}", kind="web", limit=5)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append({"query": query, "provider": name,
                                    "status": "ERROR", "error": str(exc)})
                continue
            diagnostics.extend(response.diagnostics or [])
            for result in response.results or []:
                record = _normalize(result)
                record["provider"] = name
                record["accessStatus"] = "pointer"
                raw.append(record)

    wanted = {s.lower() for s in (sources or [])} & _ACADEMIC_SOURCES
    if wanted:
        filtered = [
            r for r in raw
            if any(w in _norm(r.get("provider")) for w in wanted)
        ]
        if filtered:
            raw = filtered
        else:
            diagnostics.append({
                "status": "WARN", "warning": "SOURCE_FILTER_EMPTY",
                "detail": "no configured provider matched the requested sources; "
                          "unfiltered results are returned",
            })

    records = _dedupe(raw)
    persisted: list[dict[str, Any]] = []
    for record in records:
        try:
            saved = store.save_literature({**record, "researchId": research_id})
            persisted.append(saved)
        except QuantError:
            continue

    return {
        "status": "OK" if persisted else "UNAVAILABLE",
        "plan": plan,
        "literature": persisted,
        "diagnostics": diagnostics[:40],
        "note": (
            "A search result is a pointer, not evidence. Fetch and read the "
            "document before citing a claim or an equation."
            if persisted else
            "No scholarly results were returned. This is a search outcome, not "
            "evidence that no research exists."
        ),
    }


def get_paper(store: Any, literature_id: str) -> dict[str, Any]:
    record = store.get_literature(literature_id)
    record["papers"] = []  # populated by the caller when a method link exists
    return record


async def fetch_document(bridge: Any, url: str, *, text: str | None = None) -> dict[str, Any]:
    """Fetch a document through the existing SSRF-hardened research transport."""
    if text and str(text).strip():
        return {"status": "OK", "url": url, "text": str(text),
                "title": None, "contentHash": None, "extraction": "caller_text"}
    from ...research.web_extract import fetch

    result = await fetch(url, bridge=bridge, prefer="bridge")
    return {
        "status": "OK" if result.ok else result.status,
        "url": result.url,
        "title": result.title,
        "text": result.text if result.ok else "",
        "contentHash": result.contentHash,
        "extraction": result.extraction,
        "error": result.error,
    }


def citation_graph(
    store: Any, literature_id: str, *, direction: str = "both", depth: int = 1,
) -> dict[str, Any]:
    """Return the citation neighbourhood we actually hold metadata for.

    The registry returns pointers, not a citation database. We therefore use the
    references stored on the record and report an empty edge set honestly rather
    than inventing citations.
    """
    root = store.get_literature(literature_id)
    nodes = [{ "id": root["id"], "title": root["title"], "year": root.get("year") }]
    edges: list[dict[str, Any]] = []
    refs = root.get("references") or []
    for ref in refs if direction in ("references", "both") else []:
        if not isinstance(ref, dict):
            continue
        target = ref.get("literatureId") or (
            f"doi:{ref['doi']}" if ref.get("doi") else
            f"title:{ref.get('title')}"
        )
        if not target:
            continue
        if not any(node["id"] == target for node in nodes):
            nodes.append({"id": target, "title": ref.get("title"),
                          "doi": ref.get("doi"), "stored": False})
        edges.append({"from": root["id"], "to": target,
                      "relation": "references"})
    return {
        "root": root["id"],
        "direction": direction,
        "depth": max(1, min(int(depth or 1), 3)),
        "nodes": nodes,
        "edges": edges,
        "note": (
            "Citation edges are returned only when a stored record carries a "
            "literatureId. A missing edge means the metadata is absent, not that "
            "the papers are unrelated."
        ),
    }


__all__ = [
    "citation_graph",
    "fetch_document",
    "get_paper",
    "search_literature",
]
