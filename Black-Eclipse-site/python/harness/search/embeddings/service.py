"""EmbeddingService — the single entry point the search layer uses.

Resolves a provider from config + the run's ``ModelSettings`` credentials,
applies the content cache, batches (with retry/backoff), and reports honest
availability. When no provider is configured, ``available`` is False and the
caller degrades to keyword/FTS search — semantic search is never faked.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ..config import SearchConfig
from ..errors import EmbeddingUnavailable
from .base import EmbeddingProvider
from .batcher import BatchEmbedResult, EmbeddingBatcher
from .cache import EmbeddingCache, cache_key
from .providers import (
    CohereEmbeddingProvider,
    GoogleEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    VoyageEmbeddingProvider,
)
from .registry import EmbeddingModelRegistry

# How long a tripped circuit stays open before a resolution may re-probe the
# provider. `configure()` runs on every search/ingest, so an un-cooled reset
# re-armed a permanently broken endpoint once per query.
CIRCUIT_COOLDOWN_S = 30.0

_PROVIDER_CLASSES: dict[str, type[EmbeddingProvider]] = {
    "openai": OpenAICompatibleEmbeddingProvider,
    "google": GoogleEmbeddingProvider,
    "cohere": CohereEmbeddingProvider,
    "voyage": VoyageEmbeddingProvider,
}


@dataclass
class EmbeddingOutcome:
    vectors: list[Optional[list[float]]]
    cache_hits: int = 0
    cache_misses: int = 0
    failures: int = 0
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.failures == 0 and all(v is not None for v in self.vectors)


class EmbeddingService:
    def __init__(
        self,
        config: SearchConfig,
        *,
        cache: Optional[EmbeddingCache] = None,
        registry: Optional[EmbeddingModelRegistry] = None,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.config = config
        self.registry = registry or EmbeddingModelRegistry()
        self.cache = cache
        self._on_event = on_event
        self._provider: Optional[EmbeddingProvider] = None
        self._provider_model = ""
        self._available = False
        self._reason = "not configured"
        # A provider that rejects EVERY input in a batch (a 404 endpoint, a bad
        # base URL, a missing model) is not going to accept the next document
        # either. Tripping this circuit once keeps a boot warm-index from firing
        # thousands of doomed requests — the index degrades to keyword-only until
        # `configure()` resolves the provider again.
        self._circuit_open = False
        self._circuit_reason = ""
        self._circuit_opened_at = 0.0
        # Where the current resolution came from: explicit (operator/UI),
        # env (HARNESS_SEARCH_EMBEDDING_*), run (the chat provider's settings),
        # or none. Surfaced so the UI can explain *why* semantic search is off.
        self._source = "none"
        self._last_settings: Any = None
        self.last_stats: dict[str, Any] = {}

    # ── resolution ──────────────────────────────────────────────────────────

    def configure(self, settings: Any = None, overrides: Optional[dict[str, Any]] = None) -> None:
        """(Re)resolve the provider from config + optional run settings.

        Idempotent: resolving the same (provider, model, key, url) reuses the
        existing provider instance (and its connection pool).
        """
        overrides = overrides or {}
        if settings is not None:
            self._last_settings = settings
        if overrides.get("embedding_provider"):
            self._source = "explicit"
        elif self.config.embedding_provider:
            self._source = "env"
        elif self._provider_from_settings(settings):
            self._source = "run"
        else:
            self._source = "none"
        provider_id = (
            overrides.get("embedding_provider")
            or self.config.embedding_provider
            or self._provider_from_settings(settings)
        )
        if not provider_id:
            self._provider = None
            self._available = False
            self._reason = "no embedding provider configured"
            return

        model = overrides.get("embedding_model") or self.config.embedding_model
        if not model:
            model = self.registry.default_model(provider_id) or ""
        if not model:
            self._provider = None
            self._available = False
            self._reason = f"no embedding model declared for provider '{provider_id}'"
            return

        info = self.registry.get(provider_id, model)
        dimensions = (
            overrides.get("embedding_dimensions")
            or self.config.embedding_dimensions
            or (info.dimensions if info else 0)
        )
        version = overrides.get("embedding_version") or self.config.embedding_version
        if info is not None:
            version = info.version or version

        cached_key = self._provider_model
        if self._provider is not None and cached_key == f"{provider_id}/{model}@{version}":
            self._available = True
            # `configure()` is called on EVERY search/ingest. Resetting the
            # circuit here re-armed a provider that rejected every input (wrong
            # endpoint, missing model) once per query, producing thousands of
            # doomed HTTP calls. Keep it open for a bounded cooldown; only then
            # allow one more probe.
            if self._circuit_open and (
                time.monotonic() - self._circuit_opened_at
            ) < CIRCUIT_COOLDOWN_S:
                return
            self._reset_circuit()
            return

        api_key, base_url = self._credentials(provider_id, settings)
        cls = _PROVIDER_CLASSES.get(provider_id)
        if cls is None and self.registry.is_openai_compatible(provider_id):
            cls = OpenAICompatibleEmbeddingProvider
        if cls is None:
            self._provider = None
            self._available = False
            self._reason = f"provider '{provider_id}' does not support embeddings"
            return

        try:
            self._provider = cls(
                provider_id=provider_id,
                model=model,
                dimensions=int(dimensions or 0),
                api_key=api_key,
                base_url=base_url,
                version=version,
                timeout=self.config.embedding_timeout_s,
            )
            self._provider_model = f"{provider_id}/{model}@{version}"
            self._available = True
            self._reason = ""
            self._reset_circuit()
        except Exception as exc:  # noqa: BLE001 - constructor must never crash boot
            self._provider = None
            self._available = False
            self._reason = f"could not build embedding provider: {exc}"

    def _provider_from_settings(self, settings: Any) -> Optional[str]:
        provider = getattr(settings, "provider", None)
        if provider:
            return provider
        return None

    def _credentials(self, provider_id: str, settings: Any) -> tuple[Optional[str], Optional[str]]:
        api_key: Optional[str] = None
        base_url: Optional[str] = None
        if settings is not None and getattr(settings, "provider", None) == provider_id:
            api_key = getattr(settings, "api_key", None)
            base_url = getattr(settings, "base_url", None)
        # Dedicated embedding overrides.
        api_key = os.environ.get("HARNESS_SEARCH_EMBEDDING_API_KEY") or api_key
        base_url = os.environ.get("HARNESS_SEARCH_EMBEDDING_BASE_URL") or base_url
        try:
            from ...models import PROVIDER_CATALOG  # noqa: PLC0415

            spec = PROVIDER_CATALOG.get(provider_id)
            if spec is not None:
                if not api_key and spec.env_var:
                    api_key = os.environ.get(spec.env_var)
                if spec.keyless and not api_key:
                    api_key = "local"
                if not base_url:
                    base_url = spec.default_base_url
        except Exception:  # noqa: BLE001 - catalog optional in isolated tests
            pass
        return api_key, base_url

    # ── properties ──────────────────────────────────────────────────────────

    def _reset_circuit(self) -> None:
        self._circuit_open = False
        self._circuit_reason = ""
        self._circuit_opened_at = 0.0

    @property
    def available(self) -> bool:
        return self._available and not getattr(self, "_circuit_open", False) and self._provider is not None

    @property
    def reason(self) -> str:
        return getattr(self, "_circuit_reason", "") or self._reason

    @property
    def provider_id(self) -> str:
        return self._provider.get_provider() if self._provider else ""

    @property
    def model_id(self) -> str:
        return self._provider.get_model() if self._provider else ""

    @property
    def version(self) -> str:
        return self._provider.get_version() if self._provider else self.config.embedding_version

    @property
    def dimensions(self) -> int:
        return self._provider.get_dimensions() if self._provider else self.config.embedding_dimensions

    @property
    def distance_metric(self) -> str:
        return self._provider.distance_metric if self._provider else self.config.distance_metric

    def model_key(self) -> str:
        """The vector-space identity: provider/model@version. Empty when off."""
        if not self._provider:
            return ""
        return self._provider_model

    # ── status / setup ──────────────────────────────────────────────────────

    def _state(self) -> str:
        if self.available:
            if self._missing_credentials():
                return "missing_credentials"
            return "active"
        if self._circuit_open:
            return "unreachable"
        reason = self._reason.lower()
        if self._source == "none":
            return "no_provider"
        if "does not support embeddings" in reason or "no embedding model declared" in reason:
            return "unsupported_provider"
        if "no embedding model" in reason:
            return "missing_model"
        return "unavailable"

    def _hint(self, state: str, provider: str) -> str:
        if state == "active":
            return "Semantic + hybrid retrieval are live."
        if state == "missing_credentials":
            return (
                f"{provider or 'This provider'} needs an API key before it can embed. "
                "Add the key in Settings, pick another model below, or use local Ollama."
            )
        if state == "unreachable":
            return (
                "The provider rejected every request. Check the API key, base URL and "
                "that the embedding model is available, then test again."
            )
        if state == "unsupported_provider":
            return (
                f"'{provider or 'your chat provider'}' does not offer an embedding model. "
                "Pick one of the models below — they run alongside your chat model and "
                "only index text you search."
            )
        if state == "missing_model":
            return "Choose an embedding model below, or set HARNESS_SEARCH_EMBEDDING_MODEL."
        if state == "no_provider":
            return (
                "No embedding provider is configured, so search is keyword-only. "
                "Pick a model below (local Ollama needs no API key) or set "
                "HARNESS_SEARCH_EMBEDDING_PROVIDER."
            )
        return self._reason or "Embeddings are unavailable."

    def _credentials_ready(self, provider_id: str, settings: Any) -> bool:
        try:
            api_key, _ = self._credentials(provider_id, settings)
        except Exception:  # noqa: BLE001 - status must never crash
            return False
        return bool(api_key)

    def _missing_credentials(self) -> bool:
        """True when a hosted provider is selected but no key can be resolved.

        Construction succeeds without a key (the check is an HTTP call away), so
        without this a keyless OpenAI setup would advertise "live" and then fail
        on the first embed.
        """
        if self._provider is None:
            return False
        try:
            api_key, _ = self._credentials(self.provider_id, self._last_settings)
        except Exception:  # noqa: BLE001
            return False
        return not api_key

    def _suggestions(self, limit: int = 4) -> list[dict[str, Any]]:
        """Declared embedding models the operator can switch to right now.

        One representative model per provider, ordered by how likely it is to
        work without extra setup: already-configured first, then credentialed
        providers, then local (keyless) servers, then the rest.
        """
        seen: set[str] = set()
        rows: list[dict[str, Any]] = []
        for info in self.registry.list_models(active_only=True):
            if info.provider in seen:
                continue
            seen.add(info.provider)
            ready = self._credentials_ready(info.provider, self._last_settings)
            local = info.provider in ("ollama", "lmstudio", "local")
            rows.append(
                {
                    "provider": info.provider,
                    "model": info.model,
                    "dimensions": int(info.dimensions or 0),
                    "label": f"{info.provider}/{info.model}",
                    "credentialsReady": ready,
                    "local": local,
                }
            )

        def _rank(row: dict[str, Any]) -> tuple[int, str]:
            if row["provider"] == self.provider_id and self.available:
                return (0, row["provider"])
            if row["credentialsReady"] and not row["local"]:
                return (1, row["provider"])
            if row["local"]:
                return (2, row["provider"])
            return (3, row["provider"])

        rows.sort(key=_rank)
        return rows[:limit]

    def resolution(self) -> dict[str, Any]:
        """A structured, honest explanation of the embedding state.

        The UI renders this instead of a bare "unavailable": every off state
        carries a reason, a next step, and concrete models to switch to.
        """
        state = self._state()
        provider = self.provider_id or self.config.embedding_provider or ""
        hint = self._hint(state, provider)
        return {
            "state": state,
            "source": self._source,
            "available": state == "active",
            "reason": self.reason or ("" if state == "active" else hint),
            "hint": hint,
            "provider": provider,
            "model": self.model_id or self.config.embedding_model or "",
            "dimensions": int(self.dimensions or 0),
            "distanceMetric": self.distance_metric,
            "suggestions": [] if state == "active" else self._suggestions(),
        }

    # ── embedding ───────────────────────────────────────────────────────────

    async def embed_texts(self, texts: list[str], *, bypass_cache: bool = False) -> EmbeddingOutcome:
        if not texts:
            return EmbeddingOutcome(vectors=[])
        if not self.available:
            raise EmbeddingUnavailable(self._reason or "embedding provider unavailable")
        assert self._provider is not None

        keys = [
            cache_key(t, self._provider.provider_id, self._provider.model, self._provider.version)
            for t in texts
        ]
        vectors: list[Optional[list[float]]] = [None] * len(texts)
        hits = 0
        pending: list[int] = []
        use_cache = self.cache is not None and self.config.cache_enabled and not bypass_cache

        if use_cache:
            found = self.cache.get_many(keys)  # type: ignore[union-attr]
            for i, key in enumerate(keys):
                if key in found:
                    vectors[i] = found[key]
                    hits += 1
                else:
                    pending.append(i)
        else:
            pending = list(range(len(texts)))

        batcher = EmbeddingBatcher(
            self._provider,
            batch_size=self.config.batch_size,
            max_batch_chars=self.config.max_batch_chars,
            max_retries=self.config.embedding_max_retries,
            backoff_base=self.config.embedding_backoff_base,
            backoff_cap=self.config.embedding_backoff_cap,
            timeout_s=self.config.embedding_timeout_s,
            requests_per_minute=self.config.embedding_requests_per_minute,
            on_event=self._on_event,
        )
        elapsed = 0.0
        failures = 0
        if pending:
            batch_result: BatchEmbedResult = await batcher.embed([texts[i] for i in pending])
            elapsed = batch_result.elapsed_ms
            failures = batch_result.failures
            # Every input in this call failed and produced no vector at all. That
            # is a provider-wide rejection (404 / wrong endpoint / missing model),
            # not a partial batch: open the circuit so the caller stops asking and
            # the index stays honestly keyword-only for the rest of this pass.
            if pending and failures >= len(pending) and not any(v is not None for v in vectors):
                self._circuit_open = True
                self._circuit_opened_at = time.monotonic()
                self._circuit_reason = (
                    f"embedding provider rejected all {len(pending)} input(s); "
                    "semantic indexing disabled until reconfigured"
                )
            new_entries: list[tuple[str, list[float]]] = []
            for slot, vector in zip(pending, batch_result.vectors):
                vectors[slot] = vector
                if vector is not None and use_cache:
                    new_entries.append((keys[slot], vector))
            if new_entries:
                assert self.cache is not None
                import time as _time

                self.cache.put_many(
                    new_entries,
                    provider=self._provider.provider_id,
                    model=self._provider.model,
                    version=self._provider.version,
                    created_at=_time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                )
                self.cache.prune()
                self.cache.commit()

        self.last_stats = {
            "cacheHits": hits,
            "cacheMisses": len(pending),
            "failures": failures,
            "elapsedMs": round(elapsed, 2),
        }
        return EmbeddingOutcome(
            vectors=vectors, cache_hits=hits, cache_misses=len(pending), failures=failures, elapsed_ms=elapsed
        )

    async def embed_query(self, text: str) -> Optional[list[float]]:
        if not self.available:
            return None
        outcome = await self.embed_texts([text])
        return outcome.vectors[0] if outcome.vectors else None


__all__ = ["EmbeddingOutcome", "EmbeddingService"]
