"""Opt-in live embedding smoke test.

Skipped unless BLACK_ECLIPSE_SEARCH_LIVE=1 and an embedding provider is
configured. This is the ONLY test that contacts a real provider; the rest of the
search suite is offline and deterministic. Run it before a release once a key is
available:

    set BLACK_ECLIPSE_SEARCH_LIVE=1
    set HARNESS_SEARCH_EMBEDDING_PROVIDER=openai
    set HARNESS_SEARCH_EMBEDDING_MODEL=text-embedding-3-small
    set OPENAI_API_KEY=...
    pytest python/tests/test_search_live.py
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("BLACK_ECLIPSE_SEARCH_LIVE") not in ("1", "true", "yes", "on")
    or not os.environ.get("HARNESS_SEARCH_EMBEDDING_PROVIDER"),
    reason="live search smoke is opt-in: set BLACK_ECLIPSE_SEARCH_LIVE=1 and an embedding provider",
)


def test_live_embeddings_and_similarity():
    from harness.search.live_smoke import _run

    import asyncio

    result = asyncio.run(_run())
    if result.get("configured") is False:
        pytest.skip(f"provider unavailable: {result.get('reason')}")
    assert result["ok"], result
