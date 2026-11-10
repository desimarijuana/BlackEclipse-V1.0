"""Search / news / academic / image / video provider abstraction + registry.

Design rule: the engine NEVER hard-codes a search provider. Everything above this
layer speaks only the normalized `SearchResponse`/`SearchResult` contracts. A
provider is a small adapter that turns one backend into that contract.

The default configured route is the existing Eclipse web search capability
(`web_search` on the `DataBridge`), which itself already contains a multi-provider
fallback chain (DuckDuckGo keyless + operator-configured custom provider) and an
SSRF-hardened transport. This module does not duplicate that chain: it wraps it,
and adds an explicit, ordered, health-aware registry so a research run can name
its providers, prefer primary sources, and fall back without dying.

No provider that requires credentials is enabled unless configuration supplies
them; credential-requiring providers report `configured=False` and are skipped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, runtime_checkable

from .web_contracts import SearchResponse, SearchResult

# ── Provider contract ──────────────────────────────────────────────────────────


@runtime_checkable
class SearchProvider(Protocol):
    """A search backend adapter. Returns a normalized `SearchResponse`."""

    name: str
    capabilities: tuple[str, ...]

    def available(self) -> bool: ...

    async def search(self, query: str, *, limit: int = 8, **kwargs: Any) -> SearchResponse: ...


@dataclass
class ProviderInfo:
    name: str
    kind: str  # web | news | academic | image | video
    priority: int = 100
    cost: float = 0.0
    avgLatencyMs: int = 0
    reliability: float = 1.0
    rateLimitPerMin: Optional[int] = None
    requiresCredentials: bool = False
    capabilities: tuple[str, ...] = ()
    available: bool = False
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "priority": self.priority,
            "cost": self.cost,
            "avgLatencyMs": self.avgLatencyMs,
            "reliability": self.reliability,
            "rateLimitPerMin": self.rateLimitPerMin,
            "requiresCredentials": self.requiresCredentials,
            "capabilities": list(self.capabilities),
            "available": self.available,
            "note": self.note,
        }


# ── Bridge-backed provider (the configured default route) ──────────────────────


class BridgeSearchProvider:
    """The Eclipse web-search capability, reached through `DataBridge`.

    The bridge owns the real provider chain and SSRF transport; this adapter
    normalizes its response. A missing bridge is an honest unavailability.
    """

    def __init__(self, bridge: Any, *, name: str = "eclipse_bridge") -> None:
        self._bridge = bridge
        self.name = name
        self.capabilities = ("web", "news")

    def available(self) -> bool:
        return self._bridge is not None

    async def search(self, query: str, *, limit: int = 8, **kwargs: Any) -> SearchResponse:
        if self._bridge is None:
            return SearchResponse(query=query, status="UNAVAILABLE", error="data bridge not configured")
        import time

        started = time.monotonic()
        try:
            payload = await self._bridge.fetch(
                "web_search",
                {"query": query, "limit": max(1, min(int(limit), 15))},
            )
        except Exception as exc:  # noqa: BLE001 - a provider error is an unavailable answer
            return SearchResponse(query=query, status="ERROR", error=str(exc), provider=self.name)
        latency = int((time.monotonic() - started) * 1000)
        if payload.get("status") != "OK":
            return SearchResponse(
                query=query,
                status="UNAVAILABLE",
                provider=self.name,
                failureClass=payload.get("failureClass"),
                error=payload.get("error") or "search returned no results",
                diagnostics=list(payload.get("diagnostics") or []),
                latencyMs=latency,
            )
        results = _normalize_results(payload.get("results") or [], provider=self.name, query=query)
        return SearchResponse(
            query=query,
            status="OK",
            provider=payload.get("provider") or self.name,
            results=results,
            diagnostics=list(payload.get("diagnostics") or []),
            latencyMs=latency,
        )


def _normalize_results(raw: list[dict[str, Any]], *, provider: str, query: str) -> list[SearchResult]:
    from urllib.parse import urlparse

    from .web_sources import classify_source_type

    out: list[SearchResult] = []
    for idx, item in enumerate(raw):
        # Image capabilities return the normalized ImageSearchResult contract
        # (`imageUrl`/`sourceUrl`); ordinary search returns `url`. Accept both so
        # the research registry can consume an image connector unchanged.
        url = str(item.get("url") or item.get("sourceUrl") or item.get("imageUrl") or "").strip()
        if not url:
            continue
        try:
            domain = str(item.get("sourceDomain") or "").strip() or urlparse(url).netloc.lower().replace("www.", "")
        except Exception:  # noqa: BLE001
            domain = ""
        out.append(
            SearchResult(
                resultId=f"r{idx + 1}",
                title=str(item.get("title") or "").strip(),
                url=url,
                domain=domain,
                snippet=str(item.get("snippet") or "").strip(),
                publishedAt=item.get("publishedAt"),
                updatedAt=item.get("updatedAt"),
                author=item.get("author"),
                sourceType=classify_source_type(domain, url),
                provider=provider,
                ranking=idx,
                relevance=float(item.get("relevance") or 0.0),
                pdfUrl=item.get("pdfUrl"),
                isOpenAccess=bool(item.get("isOpenAccess")),
                references=list(item.get("references") or []),
            )
        )
    return out


# ── Structured connector provider (academic / news / image / video) ────────────


class ConnectorSearchProvider:
    """A first-class academic/news/image/video connector reached via the bridge.

    The front door owns the real keyless connectors (OpenAlex, Crossref, arXiv,
    GDELT, Openverse, Wikimedia Commons) and the SSRF transport; this adapter
    only normalizes. `kind` is one of academic|news|image|video; the bridge
    capability is `<kind>_search`. A missing bridge is an honest unavailability.
    """

    def __init__(self, bridge: Any, *, kind: str, name: Optional[str] = None) -> None:
        self._bridge = bridge
        self.kind = kind
        self.name = name or f"eclipse_{kind}"
        self.capabilities = (kind,)

    def available(self) -> bool:
        return self._bridge is not None

    async def search(self, query: str, *, limit: int = 8, **kwargs: Any) -> SearchResponse:
        if self._bridge is None:
            return SearchResponse(query=query, status="UNAVAILABLE", error="data bridge not configured", provider=self.name)
        import time

        started = time.monotonic()
        try:
            payload = await self._bridge.fetch(
                f"{self.kind}_search",
                {"query": query, "limit": max(1, min(int(limit), 25))},
            )
        except Exception as exc:  # noqa: BLE001
            return SearchResponse(query=query, status="ERROR", error=str(exc), provider=self.name)
        latency = int((time.monotonic() - started) * 1000)
        if payload.get("status") != "OK":
            return SearchResponse(
                query=query,
                status="UNAVAILABLE",
                provider=self.name,
                failureClass=payload.get("failureClass"),
                error=payload.get("error") or f"{self.kind} search returned no results",
                diagnostics=list(payload.get("diagnostics") or []),
                latencyMs=latency,
            )
        results = _normalize_results(payload.get("results") or [], provider=self.name, query=query)
        return SearchResponse(
            query=query,
            status="OK",
            provider=payload.get("provider") or self.name,
            results=results,
            diagnostics=list(payload.get("diagnostics") or []),
            latencyMs=latency,
        )


# ── Registry ───────────────────────────────────────────────────────────────────


class SearchProviderRegistry:
    """The ONE ordered registry of search/news/academic/image/video providers.

    Providers are attempted in ascending `priority` (lower = earlier). A failed
    provider falls through to the next; the run records every attempt. This is the
    "never let one provider failure kill a research run" mechanism.
    """

    def __init__(self) -> None:
        self._providers: dict[str, tuple[SearchProvider, ProviderInfo]] = {}

    def register(self, provider: SearchProvider, *, kind: str = "web", priority: int = 100, **info: Any) -> None:
        if provider.name in self._providers:
            raise ValueError(f"provider {provider.name!r} is already registered")
        meta = ProviderInfo(
            name=provider.name,
            kind=kind,
            priority=priority,
            capabilities=tuple(getattr(provider, "capabilities", ())),
            **{k: v for k, v in info.items() if k in ProviderInfo.__dataclass_fields__ and k not in ("name", "kind", "priority", "capabilities")},
        )
        self._providers[provider.name] = (provider, meta)

    def unregister(self, name: str) -> bool:
        return self._providers.pop(name, None) is not None

    def get(self, name: str) -> Optional[SearchProvider]:
        entry = self._providers.get(name)
        return entry[0] if entry else None

    def list(self) -> list[ProviderInfo]:
        infos = []
        for provider, meta in self._providers.values():
            available = False
            try:
                available = bool(provider.available())
            except Exception:  # noqa: BLE001
                available = False
            meta.available = available
            infos.append(meta)
        return sorted(infos, key=lambda m: (m.priority, m.name))

    def health(self) -> dict[str, Any]:
        return {m.name: m.to_dict() for m in self.list()}

    def available_names(self, kind: Optional[str] = None) -> list[str]:
        return [m.name for m in self.list() if m.available and (kind is None or m.kind == kind)]

    def fallback_order(self, kind: str = "web") -> list[str]:
        return [m.name for m in self.list() if m.kind == kind]

    async def search(
        self,
        query: str,
        *,
        kind: str = "web",
        limit: int = 8,
        preference: Optional[str] = None,
        max_attempts: int = 3,
        **kwargs: Any,
    ) -> SearchResponse:
        """Search with ordered fallback. Returns the first OK response.

        Every attempt is recorded in `diagnostics`. If all providers fail, the
        response is `UNAVAILABLE` with the full attempt trail — never a silent
        empty result.
        """
        order = [m for m in self.list() if m.kind == kind]
        if preference:
            order.sort(key=lambda m: (0 if m.name == preference else 1, m.priority))
        diagnostics: list[dict[str, Any]] = []
        attempts = 0
        for meta in order:
            if not meta.available:
                diagnostics.append({"provider": meta.name, "normalizedStatus": "skipped", "category": "unavailable", "detail": meta.note})
                continue
            if attempts >= max_attempts:
                break
            provider = self._providers[meta.name][0]
            attempts += 1
            try:
                response = await provider.search(query, limit=limit, **kwargs)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append({"provider": meta.name, "normalizedStatus": "failed", "category": "provider_failure", "detail": str(exc)})
                continue
            diagnostics.extend(response.diagnostics or [])
            if response.status == "OK" and response.results:
                response.diagnostics = diagnostics
                return response
            diagnostics.append({
                "provider": meta.name,
                "normalizedStatus": "failed" if response.status == "ERROR" else "empty",
                "category": response.failureClass or ("provider_failure" if response.status == "ERROR" else "no_data"),
                "detail": response.error,
            })
        return SearchResponse(
            query=query,
            status="UNAVAILABLE",
            failureClass="source_failure" if attempts else "no_data",
            error="no configured provider could answer this query",
            diagnostics=diagnostics,
        )


_GLOBAL: Optional[SearchProviderRegistry] = None


def build_default_registry(bridge: Any = None) -> SearchProviderRegistry:
    """Build the default registry for a run.

    The bridge-backed provider is the configured default. Additional providers
    (e.g. a direct academic API) can be registered by a caller; nothing that needs
    credentials is auto-registered.
    """
    registry = SearchProviderRegistry()
    if bridge is not None:
        registry.register(BridgeSearchProvider(bridge), kind="web", priority=10)
        registry.register(BridgeSearchProvider(bridge, name="eclipse_bridge_news"), kind="news", priority=10)
        # First-class keyless structured connectors, ahead of web fallback for
        # their kind. A connector failure falls through to the next provider for
        # the same kind (the caller registers a web fallback as needed).
        registry.register(ConnectorSearchProvider(bridge, kind="academic"), kind="academic", priority=20, requiresCredentials=False)
        registry.register(ConnectorSearchProvider(bridge, kind="image"), kind="image", priority=20, requiresCredentials=False)
        registry.register(ConnectorSearchProvider(bridge, kind="video"), kind="video", priority=20, requiresCredentials=False)
    return registry


def get_registry() -> Optional[SearchProviderRegistry]:
    return _GLOBAL


def set_registry(registry: Optional[SearchProviderRegistry]) -> None:
    global _GLOBAL
    _GLOBAL = registry


__all__ = [
    "SearchProvider",
    "ProviderInfo",
    "BridgeSearchProvider",
    "SearchProviderRegistry",
    "build_default_registry",
    "get_registry",
    "set_registry",
]
