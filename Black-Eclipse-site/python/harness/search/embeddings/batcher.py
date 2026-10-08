"""Batching, rate limiting, retry and backoff for embedding calls.

Never 1-chunk/1-request when the provider supports batching. A permanent batch
failure does not poison the whole call: ``BatchEmbedResult`` reports which inputs
failed so the caller can retry, skip, or fall back to keyword search.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..errors import EmbeddingProviderError as SearchEmbeddingError
from .base import EmbeddingProvider, EmbeddingProviderError


@dataclass
class BatchEmbedResult:
    vectors: list[Optional[list[float]]] = field(default_factory=list)
    failures: int = 0
    batches: int = 0
    retries: int = 0
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.failures == 0

    @property
    def vectors_present(self) -> list[list[float]]:
        return [v for v in self.vectors if v is not None]


class RateLimiter:
    """A monotonic fixed-window limiter (requests per minute)."""

    def __init__(self, requests_per_minute: int) -> None:
        self.limit = max(1, requests_per_minute)
        self._window_start = time.monotonic()
        self._count = 0

    async def acquire(self) -> None:
        now = time.monotonic()
        if now - self._window_start >= 60.0:
            self._window_start = now
            self._count = 0
        if self._count >= self.limit:
            wait = 60.0 - (now - self._window_start)
            if wait > 0:
                await asyncio.sleep(wait)
            self._window_start = time.monotonic()
            self._count = 0
        self._count += 1


def _chunk_texts(texts: list[str], batch_size: int, max_chars: int) -> list[list[int]]:
    """Partition text indices into batches respecting count and char budgets."""
    batches: list[list[int]] = []
    current: list[int] = []
    current_chars = 0
    for index, text in enumerate(texts):
        length = len(text)
        if current and (len(current) >= batch_size or current_chars + length > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(index)
        current_chars += length
    if current:
        batches.append(current)
    return batches


class EmbeddingBatcher:
    def __init__(
        self,
        provider: EmbeddingProvider,
        *,
        batch_size: int = 64,
        max_batch_chars: int = 96_000,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 8.0,
        timeout_s: float = 30.0,
        requests_per_minute: int = 600,
        allow_partial: bool = True,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ) -> None:
        self.provider = provider
        self.batch_size = max(1, batch_size)
        self.max_batch_chars = max(1, max_batch_chars)
        self.max_retries = max(0, max_retries)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self.timeout_s = timeout_s
        self.allow_partial = allow_partial
        self._limiter = RateLimiter(requests_per_minute)
        self._on_event = on_event

    def _emit(self, event: str, data: dict) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event, data)
        except Exception:  # noqa: BLE001 - observability must never break embedding
            pass

    async def embed(self, texts: list[str]) -> BatchEmbedResult:
        result = BatchEmbedResult(vectors=[None] * len(texts))
        if not texts:
            return result
        started = time.monotonic()
        batches = _chunk_texts(texts, self.batch_size, self.max_batch_chars)
        result.batches = len(batches)
        for batch in batches:
            await self._embed_one_batch([texts[i] for i in batch], batch, result)
        result.elapsed_ms = (time.monotonic() - started) * 1000.0
        return result

    async def _embed_one_batch(self, batch_texts: list[str], indices: list[int], result: BatchEmbedResult) -> None:
        attempt = 0
        while True:
            await self._limiter.acquire()
            try:
                vectors = await asyncio.wait_for(
                    self.provider.embed_batch(batch_texts), timeout=self.timeout_s
                )
            except EmbeddingProviderError as exc:
                if exc.retryable and attempt < self.max_retries:
                    attempt += 1
                    result.retries += 1
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                self._fail(indices, result, str(exc))
                return
            except asyncio.TimeoutError:
                if attempt < self.max_retries:
                    attempt += 1
                    result.retries += 1
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                self._fail(indices, result, "embedding timed out")
                return
            except Exception as exc:  # noqa: BLE001 - provider libraries may raise anything
                if attempt < self.max_retries:
                    attempt += 1
                    result.retries += 1
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                self._fail(indices, result, str(exc))
                return

            if len(vectors) != len(batch_texts):
                if attempt < self.max_retries:
                    attempt += 1
                    result.retries += 1
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                self._fail(indices, result, "provider returned a mismatched vector count")
                return
            for slot, vector in zip(indices, vectors):
                result.vectors[slot] = vector
            return

    def _backoff(self, attempt: int) -> float:
        window = min(self.backoff_cap, self.backoff_base * (2 ** max(0, attempt - 1)))
        return random.uniform(0.0, window)

    def _fail(self, indices: list[int], result: BatchEmbedResult, message: str) -> None:
        result.failures += len(indices)
        self._emit("search.embedding.failed", {"count": len(indices), "error": message})
        if not self.allow_partial:
            raise SearchEmbeddingError(message)


__all__ = ["BatchEmbedResult", "EmbeddingBatcher", "RateLimiter"]
