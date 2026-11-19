"""Defect fixes for the search layer: the repository source adapter, honest
vector accounting, the recorded keyword fallback, and durable failure detail."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time

import pytest

from harness.search import adapters
from harness.search import service as service_module
from harness.search.adapters import collect_documents, documents_from_repository
from harness.search.contracts import IndexState
from harness.search.indexer import IndexResult

from search_helpers import FakeEmbeddingProvider, instrument, make_document, make_service


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


def test_repository_adapter_skips_an_installed_payload(tmp_path, monkeypatch):
    # A packaged install ships its interpreter under scripts/vendor/python. The
    # payload's own runtime is not the user's project, and indexing it blocked
    # the runtime's event loop for minutes on every boot.
    monkeypatch.setenv("HARNESS_SEARCH_INDEX_REPO", "1")
    (tmp_path / "scripts" / "vendor" / "python").mkdir(parents=True)
    (tmp_path / "python" / "harness").mkdir(parents=True)
    (tmp_path / "python" / "harness" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert documents_from_repository(tmp_path) == []


def test_collect_documents_can_skip_repository(monkeypatch):
    sentinel = make_document("repository:x", ["alpha"], namespace="repository")
    monkeypatch.setattr(adapters, "documents_from_repository", lambda: [sentinel])
    conn = sqlite3.connect(":memory:")
    # The async caller collects repository documents separately (off the loop).
    assert collect_documents(conn, include_repository=False) == []
    assert collect_documents(conn) == [sentinel]
    conn.close()


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


@pytest.mark.asyncio
async def test_index_documents_yields_to_the_event_loop(monkeypatch):
    # The indexer does synchronous SQLite/chunk work; a bulk index must yield so
    # /health and every other request keep answering (a whole runtime starved
    # for minutes on installs that indexed thousands of files).
    service, _ = make_service(rerank_enabled=False)
    documents = [make_document(f"doc-{i}", ["alpha"], namespace="memory") for i in range(30)]

    async def slow_index(store, embedder, doc, **kwargs):
        time.sleep(0.02)  # synchronous work, exactly like the real indexer
        return IndexResult(document_id=doc.document_id, state=IndexState.INDEXED.value, chunks=1)

    monkeypatch.setattr(service_module, "index_document", slow_index)
    ticks = 0
    stop = False

    async def ticker():
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.005)

    task = asyncio.create_task(ticker())
    await service.index_documents(documents)
    stop = True
    await task
    assert ticks >= 3  # the loop ran while documents were being indexed
    service.close()
