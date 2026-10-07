"""Browser → Evidence/Research Engine integration.

A page the browser actually consulted is provenance, exactly like a retrieval.
When a browser observation produces content from a real URL, this module records
it on the run's existing `source_sink` (the same `SourceCollector` every retrieval
tool feeds), so a browser-derived fact appears in the answer's Sources panel with
its URL, title and retrieval time — never fabricated, never merged into a
`claim` the runtime did not verify.

It reuses the ONE collector contract (`add_fetched_source`); it does not invent a
second provenance shape, a second citations builder, or a second evidence store.
A run with no sink (tests, gated research) simply skips collection — additive and
best-effort, and it NEVER changes a tool's returned text.
"""

from __future__ import annotations

from typing import Any, Optional


def record_browser_source(
    ctx: Any,
    *,
    url: str,
    title: Optional[str] = None,
    ok: bool = True,
    retrieved_at: Optional[str] = None,
) -> bool:
    """Record a browser-consulted URL on the run's source collector.

    Returns whether a record was made. Never raises: provenance collection must
    never break a browser action.
    """
    sink = getattr(ctx, "source_sink", None)
    if sink is None or not url:
        return False
    try:
        if hasattr(sink, "add_fetched_source"):
            sink.add_fetched_source(
                url=url, title=title, ok=ok, retrieved_at=retrieved_at,
            )
            return True
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return False
    return False


def is_page_evidence_url(url: str) -> bool:
    """Whether a URL is a real http(s) page worth recording as a source.

    An `about:blank`, a data: URI, or an internal page is not a consulted source
    and must never enter the Sources panel.
    """
    if not url:
        return False
    lowered = url.strip().lower()
    return lowered.startswith("http://") or lowered.startswith("https://")


__all__ = ["is_page_evidence_url", "record_browser_source"]
