"""Search routing, SQL safety, agent tools and semantic-shape tests."""

from __future__ import annotations

import asyncio
import types

import pytest

from harness.sources.config import load_config
from harness.sources.query import describe_source, run_sql, validate_sql
from harness.sources.semantic import SemanticIndex
from harness.sources.service import SourceService, set_sources_service
from harness.tools import ToolRegistry
from harness.sources.tools import register_source_tools


@pytest.fixture()
def service(tmp_path):
    cfg = load_config({
        "db_path": str(tmp_path / "sources.db"),
        "tmp_dir": str(tmp_path / "tmp"),
        "index_max_file_bytes": 4 * 1024 * 1024,
        "chunk_chars": 400,
        "scan_max_bytes": 2 * 1024 * 1024,
        "scan_timeout_s": 10,
    })
    svc = SourceService(cfg)
    set_sources_service(svc)
    yield svc
    svc.close()


@pytest.fixture()
def corpus(tmp_path, service):
    root_dir = tmp_path / "corpus"
    root_dir.mkdir()
    (root_dir / "notes.txt").write_text(
        "The quarterly revenue report shows margin expansion.\n" * 200, encoding="utf-8"
    )
    (root_dir / "trades.csv").write_text(
        "ticker,shares,price\nAAPL,10,190.5\nMSFT,5,410.0\nAAPL,4,191.0\n", encoding="utf-8"
    )
    (root_dir / "unindexed.log").write_text(
        "noise before\nUNIQUE_TOKEN_XYZ appears here\nnoise after\n", encoding="utf-8"
    )
    root = service.add_root(str(root_dir))
    service.wait_scan(root["id"], timeout_s=20)
    return {"root": root, "dir": root_dir}


# ── SQL ─────────────────────────────────────────────────────────────────────


def test_sql_is_exact_and_read_only(corpus):
    path = str(corpus["dir"] / "trades.csv")
    result = run_sql(path, "SELECT ticker, SUM(shares) AS total FROM t GROUP BY ticker ORDER BY ticker")
    assert result.ok, result.error
    assert result.columns == ["ticker", "total"]
    assert result.rows == [["AAPL", 14], ["MSFT", 5]]

    described = describe_source(path)
    assert described["ok"]
    assert [c["name"] for c in described["columns"]] == ["ticker", "shares", "price"]


def test_sql_refuses_escapes_and_mutation():
    for sql in (
        "INSERT INTO t VALUES (1)",
        "SELECT 1; DROP TABLE t",
        "SELECT * FROM read_csv('/etc/passwd')",
        "ATTACH 'x.db'",
        "SELECT 1 -- comment",
        "",
    ):
        assert validate_sql(sql) is not None, sql

    assert validate_sql("SELECT * FROM t LIMIT 5") is None
    assert validate_sql("WITH x AS (SELECT 1) SELECT * FROM x") is None


def test_sql_reports_unsupported_formats(tmp_path):
    path = tmp_path / "x.weird"
    path.write_text("nope", encoding="utf-8")
    result = run_sql(str(path), "SELECT * FROM t")
    assert result.ok is False
    assert "not a queryable table format" in (result.error or "")


# ── indexing + routing ──────────────────────────────────────────────────────


def test_index_builds_fts_and_planner_prefers_it(service, corpus):
    indexed = service.index(root_ids=[corpus["root"]["id"]], limit_files=10, budget_s=20)
    assert indexed["indexed"] >= 2
    stats = service.stats()
    assert stats["indexedFiles"] >= 2
    assert stats["chunks"] > 0

    result = service.search(query="revenue margin", mode="text", limit=10)
    assert result.hits
    assert "fts" in result.plan.engines
    assert result.hits[0].snippet


def test_metadata_route_answers_filename_queries(service, corpus):
    result = service.search(query="*.csv", mode="auto", limit=10)
    assert result.plan.mode == "metadata"
    assert result.hits and result.hits[0].relpath == "trades.csv"


def test_raw_scan_finds_unindexed_content_and_reports_coverage(service, corpus):
    result = service.search(query="UNIQUE_TOKEN_XYZ", mode="raw", limit=10)
    assert result.plan.engines == ["scan"]
    assert result.hits
    assert result.hits[0].relpath == "unindexed.log"
    assert result.hits[0].line == 2
    assert "UNIQUE_TOKEN_XYZ" in (result.hits[0].snippet or "")
    assert result.scanned_files >= 1


def test_raw_scan_respects_the_byte_budget(service, corpus, tmp_path):
    service.config.scan_max_bytes = 4_096
    result = service.search(query="revenue", mode="raw", limit=50)
    assert result.truncated is True
    assert any("byte budget" in w for w in result.warnings)


def test_planner_never_escapes_the_candidate_filters(service, corpus):
    result = service.search(query="revenue", mode="text", klass="table", limit=10)
    assert all(hit.klass == "table" for hit in result.hits)


def test_sql_through_the_service(service, corpus):
    result = service.sql(
        root_id=corpus["root"]["id"], relpath="trades.csv",
        sql="SELECT COUNT(*) AS n, SUM(shares) AS shares FROM t",
    )
    assert result.ok, result.error
    assert result.rows == [[3, 19]]

    all_files = service.sql(
        root_id=corpus["root"]["id"], all_root_files=True,
        sql="SELECT ticker, SUM(shares) AS n FROM t GROUP BY ticker ORDER BY ticker",
    )
    assert all_files.ok, all_files.error
    assert all_files.rows[0] == ["AAPL", 14]


# ── semantic shape ─────────────────────────────────────────────────────────


class _FakeEmbedder:
    available = True

    def model_key(self) -> str:
        return "fake/model@1"

    async def embed_texts(self, texts, **_: object):
        return types.SimpleNamespace(ok=True, vectors=[[1.0, 0.0] for _ in texts])

    async def embed_query(self, text: str):
        return [1.0, 0.0]


def test_semantic_unavailable_is_honest(service):
    assert service.semantic.available is False
    assert "disabled" in service.semantic.reason
    result = service.search(query="revenue", mode="similar", limit=5)
    assert result.hits == [] or all(h.engine == "metadata" for h in result.hits)
    assert any("semantic search is unavailable" in w for w in result.warnings)


def test_semantic_scores_a_fake_vector_space(tmp_path):
    cfg = load_config({
        "db_path": str(tmp_path / "sources.db"),
        "tmp_dir": str(tmp_path / "tmp"),
        "semantic_enabled": True,
    })
    catalog = svc_catalog(cfg)
    semantic = SemanticIndex(catalog, cfg, embedder=_FakeEmbedder())
    svc = SourceService(cfg, catalog=catalog, semantic=semantic)
    try:
        root_dir = tmp_path / "vec"
        root_dir.mkdir()
        (root_dir / "a.txt").write_text("alpha", encoding="utf-8")
        root = svc.add_root(str(root_dir))
        svc.wait_scan(root["id"], timeout_s=20)
        file = svc.catalog.get_file(root["id"], "a.txt")
        svc.catalog.put_vectors(file.id, [(0, [1.0, 0.0]), (1, [0.0, 1.0])], model="fake/model@1")
        files = [file]
        hits = svc.semantic.search_sync("anything", files, top_k=2)
        assert hits[0][0] == file.id
        assert hits[0][2] > hits[1][2]
        assert svc.semantic.available is True
    finally:
        svc.close()


def svc_catalog(cfg):
    from harness.sources.catalog import Catalog

    return Catalog(cfg)


# ── agent tools ────────────────────────────────────────────────────────────


def _ctx(service):
    return types.SimpleNamespace(run_id="test-run", sources=service)


def test_tools_register_once_and_read(service, corpus):
    registry = ToolRegistry()
    added = register_source_tools(registry)
    assert len(added) == 9
    assert register_source_tools(registry) == []

    ctx = _ctx(service)
    roots = asyncio.run(registry.execute("source_roots", "c1", {}, ctx))
    assert roots.ok and corpus["root"]["path"] in roots.text

    opened = asyncio.run(registry.execute(
        "source_open", "c2", {"root_id": corpus["root"]["id"], "relpath": "notes.txt"}, ctx
    ))
    assert opened.ok
    assert "notes.txt" in opened.text
    assert opened.data["card"]["klass"] == "text"

    searched = asyncio.run(registry.execute(
        "source_search", "c3", {"query": "UNIQUE_TOKEN_XYZ", "mode": "raw"}, ctx
    ))
    assert searched.ok
    assert "UNTRUSTED_SOURCE_CONTENT" in searched.text
    assert searched.data["hits"][0]["relpath"] == "unindexed.log"

    sql = asyncio.run(registry.execute(
        "source_sql", "c4",
        {"root_id": corpus["root"]["id"], "relpath": "trades.csv", "sql": "SELECT COUNT(*) FROM t"},
        ctx,
    ))
    assert sql.ok and "3" in sql.text

    refused = asyncio.run(registry.execute(
        "source_sql", "c5",
        {"root_id": corpus["root"]["id"], "relpath": "trades.csv", "sql": "DELETE FROM t"},
        ctx,
    ))
    assert refused.ok and "only SELECT" in refused.text

    stats = asyncio.run(registry.execute("source_stats", "c6", {}, ctx))
    assert stats.ok and stats.data["files"] >= 3

    index = asyncio.run(registry.execute(
        "source_index", "c7", {"root_ids": [corpus["root"]["id"]], "limit_files": 5}, ctx
    ))
    assert index.ok


def test_tool_schemas_are_well_formed():
    registry = ToolRegistry()
    register_source_tools(registry)
    for tool in registry.list():
        assert tool.input_schema.get("type") == "object"
        assert tool.permission == "read"
        assert tool.description
