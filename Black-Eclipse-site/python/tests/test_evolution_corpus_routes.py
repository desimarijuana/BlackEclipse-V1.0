"""Read-only corpus/rotation operator routes."""

from __future__ import annotations

from harness.evaluation.corpus import build_manifest
from harness.routers.evolution_corpus import corpus_status, rotation_preview


def test_corpus_status_is_a_compact_verified_view():
    result = corpus_status(_=True)
    assert result["success"] is True
    assert result["manifest"]["taskCount"] == build_manifest()["taskCount"]
    assert result["manifest"]["oracleExemptCount"] == build_manifest()["oracleExemptCount"]
    assert result["manifest"]["oracleCoverage"] > 0
    assert len(result["manifest"]["datasets"]) >= 10
    assert result["verification"]["ok"] is True
    assert result["audit"]["ok"] is True


def test_rotation_preview_never_writes_or_touches_validation():
    result = rotation_preview(quarter="2026Q1", count=4, _=True)
    assert result["applied"] is False
    assert result["quarter"] == "2026Q1"
    assert result["plan"]["ok"] is True
    assert all(move["to"] != "validation" for move in result["plan"]["moves"])


def test_the_routes_are_mounted():
    import harness.main as main_module

    paths = set((main_module.app.openapi() or {}).get("paths") or {})
    assert "/evolution/corpus" in paths
    assert "/evolution/corpus/rotation" in paths
