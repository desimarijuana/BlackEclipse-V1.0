"""Defect fixes for the search layer: the repository source adapter, honest
vector accounting, the recorded keyword fallback, and durable failure detail."""

from __future__ import annotations

import json

import pytest

from harness.search.adapters import documents_from_repository

from search_helpers import FakeEmbeddingProvider, instrument, make_service


def test_repository_adapter_indexes_source_files(tmp_path, monkeypatch):
    # The offline suite disables repo indexing by default (conftest); opt in here.
    monkeypatch.setenv("HARNESS_SEARCH_INDEX_REPO", "1")
    (tmp_path / "python" / "harness").mkdir(parents=True)
    (tmp_path / "python" / "harness" / "mod.py").write_text(
        "def add_portfolio_position(quantity: float, price: float) -> float:\n"
        "    return quantity * price  # position value in the base currency\n",
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text(
        "export function formatHoldings(rows: Holding[]): string[] {\n"
        "  return rows.map((row) => `${row.symbol} ${row.quantity}`);\n}\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "binary.py").write_bytes(b"\xff\xfe\x00\x01not utf8")
    docs = documents_from_repository(tmp_path)
    titles = {d.title for d in docs}
    assert "python/harness/mod.py" in titles and "src/app.ts" in titles
    assert all(d.namespace == "repository" and d.source_type == "repository" for d in docs)
    # A binary/unreadable file is skipped, never indexed as garbage.
    assert "src/binary.py" not in titles


def test_repository_adapter_is_disabled_by_env(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.py").write_text(
        "def helper(value: int) -> int:\n    return value + 1  # a small helper\n", encoding="utf-8"
    )
    monkeypatch.setenv("HARNESS_SEARCH_INDEX_REPO", "0")
    assert documents_from_repository(tmp_path) == []


@pytest.mark.asyncio
async def test_unchanged_keyword_only_reports_missing_vectors():
    # A keyword-only (STALE) document that is "unchanged" must still report its
    # chunks as missing vectors — the defect that let a 54-chunk / 0-vector index
    # look fully indexed.
    service, _ = make_service(rerank_enabled=False)
    text = "alpha beta gamma delta epsilon " * 40
    first = await service.ingest_text(
        text, title="t", source_type="filing", source_id="s", namespace="filing",
    )
    assert first.unchanged is False
    assert first.vectors == 0
    assert first.missing_vectors == first.chunks > 0  # no embedder → keyword-only
    second = await service.ingest_text(
        text, title="t", source_type="filing", source_id="s", namespace="filing",
    )
    assert second.unchanged is True
    assert second.vectors == 0
    assert second.missing_vectors == second.chunks > 0


@pytest.mark.asyncio
async def test_hybrid_fallback_is_recorded_when_query_embedding_fails(monkeypatch):
    service, _ = make_service(rerank_enabled=False)
    instrument(service, FakeEmbeddingProvider())
    await service.ingest_text(
        "nvidia revenue growth and data center demand", title="NVDA",
        source_type="filing", source_id="nvda", namespace="filing",
    )

    async def _fail(_text):
        return None

    monkeypatch.setattr(service.embedder, "embed_query", _fail)
    result = await service.hybrid("nvidia revenue")
    # The degradation is recorded structurally, not just as a warning string.
    assert result.stats.fallback == "keyword"
    assert result.stats.semantic_available is False


def test_record_event_keeps_failure_detail():
    service, _ = make_service(rerank_enabled=False)
    service.store.record_event("search.embedding.failed", {"count": 3, "error": "boom"})
    events = service.store.recent_events(limit=1, kind="search.embedding.failed")
    # Detail is preserved (JSON text on the row) so a real embedding failure is
    # diagnosable.
    detail = json.loads(events[0]["detail"])
    assert detail["count"] == 3
    assert detail["error"] == "boom"
    service.close()


def test_boot_settings_reads_the_job_env(monkeypatch):
    service, _ = make_service(rerank_enabled=False)
    # A bare runtime (no front-door env) stays honestly keyword-only.
    assert service._boot_settings() is None
    monkeypatch.setenv("HARNESS_JOB_PROVIDER", "ollama")
    monkeypatch.setenv("HARNESS_JOB_BASE_URL", "http://localhost:11434/v1")
    settings = service._boot_settings()
    assert settings.provider == "ollama"
    assert settings.base_url.endswith("/v1")


@pytest.mark.asyncio
async def test_warm_index_configures_from_the_boot_env(monkeypatch):
    # The boot warm-index must EMBED (store vectors), not run keyword-only: it
    # configures the provider from the front-door env before indexing.
    service, _ = make_service(rerank_enabled=False)
    seen: dict = {}
    monkeypatch.setattr(service, "configure", lambda settings=None, overrides=None: seen.update(settings=settings))
    monkeypatch.setenv("HARNESS_JOB_PROVIDER", "ollama")
    await service.warm_index()
    assert seen["settings"] is not None and seen["settings"].provider == "ollama"
    service.close()
