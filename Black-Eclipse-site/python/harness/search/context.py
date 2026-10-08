"""Context assembly for the agent.

Turns a ranked hit list into a bounded, deduplicated, provenance-preserving
context block. Enforces a token budget, per-source and per-document diversity
limits, and includes neighbouring context so a matched chunk is never returned
in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import SearchConfig
from .contracts import SearchHit

_CHARS_PER_TOKEN = 4


@dataclass
class AssembledContext:
    text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    used: list[SearchHit] = field(default_factory=list)
    dropped: int = 0
    tokens_estimate: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "citations": self.citations,
            "usedChunkIds": [h.chunk_id for h in self.used],
            "dropped": self.dropped,
            "tokensEstimate": self.tokens_estimate,
            "truncated": self.truncated,
        }


class ContextAssembler:
    def __init__(self, config: SearchConfig) -> None:
        self.config = config

    def assemble(self, hits: list[SearchHit], *, query: str = "") -> AssembledContext:
        budget_tokens = self.config.context_max_tokens
        budget_chars = budget_tokens * _CHARS_PER_TOKEN
        per_source = self.config.context_per_source_limit
        per_document = self.config.context_per_document_limit

        source_counts: dict[str, int] = {}
        document_counts: dict[str, int] = {}
        blocks: list[str] = []
        citations: list[dict[str, Any]] = []
        used: list[SearchHit] = []
        chars = 0
        dropped = 0
        truncated = False

        for hit in hits:
            source_key = hit.provenance.source_id or hit.provenance.source_type or hit.document_id
            if self.config.context_diversity:
                if source_counts.get(source_key, 0) >= per_source:
                    dropped += 1
                    continue
                if document_counts.get(hit.document_id, 0) >= per_document:
                    dropped += 1
                    continue
            block = self._render_block(hit)
            if chars + len(block) > budget_chars:
                remaining = budget_chars - chars
                if remaining < 200:
                    dropped += 1
                    continue
                block = block[:remaining] + "…"
                truncated = True
            source_counts[source_key] = source_counts.get(source_key, 0) + 1
            document_counts[hit.document_id] = document_counts.get(hit.document_id, 0) + 1
            blocks.append(block)
            used.append(hit)
            citations.append(hit.citation.to_dict())
            chars += len(block)
            if chars >= budget_chars:
                truncated = True
                remaining = len(hits) - len(used)
                dropped += max(0, remaining)
                break

        text = "\n\n".join(blocks)
        return AssembledContext(
            text=text,
            citations=citations,
            used=used,
            dropped=dropped,
            tokens_estimate=chars // _CHARS_PER_TOKEN,
            truncated=truncated,
        )

    def _render_block(self, hit: SearchHit) -> str:
        header = hit.citation.label or hit.provenance.source_id or hit.document_id
        locator = []
        if hit.provenance.section:
            locator.append(f"§ {hit.provenance.section}")
        if hit.provenance.page is not None:
            locator.append(f"p.{hit.provenance.page}")
        if hit.published_at:
            locator.append(hit.published_at)
        suffix = f" ({', '.join(locator)})" if locator else ""
        body = hit.content
        neighbors = hit.neighbors or {}
        extra: list[str] = []
        for prev in (neighbors.get("previous") or [])[-1:]:
            extra.append(f"[preceding] {prev.get('content', '')[:400]}")
        for nxt in (neighbors.get("next") or [])[:1]:
            extra.append(f"[following] {nxt.get('content', '')[:400]}")
        tail = ("\n" + "\n".join(extra)) if extra else ""
        return f"[{hit.chunk_id}] {header}{suffix}\n{body}{tail}"


__all__ = ["AssembledContext", "ContextAssembler"]
