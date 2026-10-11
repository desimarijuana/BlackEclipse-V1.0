"""Immutable, content-addressed strategy versions + schema identity + diff."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.quant import data as D
from harness.quant import engine as E
from harness.quant import fixtures as F
from harness.quant import strategy as S
from harness.quant.errors import StrategyVersionImmutable
from harness.quant.schema import (
    STRATEGY_SCHEMA_VERSION,
    check_schema,
    migrate,
    schema_compatible,
    spec_content_hash,
)
from harness.quant.store import QuantStore


@pytest.fixture()
def store(tmp_path) -> QuantStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return QuantStore(ams, artifact_root=str(tmp_path / "art"))


def _spec(version="1.0.0", name="EMA", sizing=90):
    return S.parse_strategy({
        "strategy": {"id": "ema", "name": name, "version": version},
        "universe": {"symbols": ["TESTUSDT"]},
        "indicators": [{"id": "ema_f", "type": "ema", "params": {"period": 5}},
                       {"id": "ema_s", "type": "ema", "params": {"period": 20}}],
        "rules": {"entry": {"long": {"conditions": [
            {"left": {"ref": "ema_f"}, "op": "cross_above", "right": {"ref": "ema_s"}}]}},
            "exit": {}},
        "position_sizing": {"type": "percent_equity", "value": sizing},
    })


def _with_experiment(store, spec):
    """Persist a strategy version and one experiment that references it."""
    store.save_strategy(spec)
    rows = F.bull_market("TESTUSDT", n=200)
    ds = D.build_dataset({"TESTUSDT": D.series_from_rows("TESTUSDT", "1d", rows, source="synthetic")})
    res = E.run_backtest(spec, ds, E.BacktestConfig(initial_capital=100_000))
    return store.save_experiment(res, strategy_id=spec.id, strategy_version=spec.version,
                                 kind="backtest")


# ── Content hash ─────────────────────────────────────────────────────────────

def test_content_hash_is_stable_and_sensitive():
    a = _spec()
    assert spec_content_hash(a) == spec_content_hash(a)
    # Re-parsing the same JSON yields the same hash.
    assert spec_content_hash(a) == spec_content_hash(S.parse_strategy(a.to_dict()))
    b = _spec(sizing=50)
    assert spec_content_hash(a) != spec_content_hash(b)


def test_store_records_content_hash(store):
    spec = _spec()
    store.save_strategy(spec)
    meta = store.version_meta("ema", "1.0.0")
    assert meta["contentHash"] == spec_content_hash(spec)
    assert meta["schemaVersion"] == STRATEGY_SCHEMA_VERSION
    assert meta["experimentCount"] == 0
    assert meta["immutable"] is False


# ── Immutability ─────────────────────────────────────────────────────────────

def test_version_immutable_after_experiment_reference(store):
    spec = _spec()
    _with_experiment(store, spec)
    assert store.version_meta("ema", "1.0.0")["immutable"] is True

    # Same content re-save is a no-op (allowed).
    store.save_strategy(_spec())

    # Different content under the SAME version is refused once referenced.
    with pytest.raises(StrategyVersionImmutable) as exc:
        store.save_strategy(_spec(sizing=50))
    assert exc.value.code == "STRATEGY_VERSION_IMMUTABLE"

    # Bumping the version is the sanctioned path.
    store.save_strategy(_spec(version="1.1.0", sizing=50))
    assert len(store.list_versions("ema")) == 2


def test_version_overwrite_allowed_when_unreferenced(store):
    store.save_strategy(_spec())
    # No experiment references this version: a correction is allowed.
    store.save_strategy(_spec(sizing=42))
    assert store.get_strategy("ema")["spec"]["position_sizing"]["value"] == 42


# ── Diff ─────────────────────────────────────────────────────────────────────

def test_diff_versions_reports_structural_changes(store):
    store.save_strategy(_spec(version="1.0.0"))
    store.save_strategy(_spec(version="1.1.0", sizing=50))
    diff = store.diff_versions("ema", "1.0.0", "1.1.0")
    assert diff["sameContent"] is False
    assert diff["changeCount"] >= 2  # version + sizing value
    paths = {c["path"] for c in diff["changes"]}
    assert "position_sizing.value" in paths
    assert "version" in paths
    assert "position_sizing" in diff["bySection"]


def test_diff_versions_identical(store):
    store.save_strategy(_spec(version="1.0.0"))
    store.save_strategy(_spec(version="1.1.0"))
    # Only the version field differs.
    diff = store.diff_versions("ema", "1.0.0", "1.1.0")
    assert diff["changeCount"] == 1
    assert diff["changes"][0]["path"] == "version"


# ── Schema identity / migration ──────────────────────────────────────────────

def test_schema_compatibility():
    assert schema_compatible(None) is True
    assert schema_compatible("1.0.0") is True
    assert schema_compatible("1.2.0") is True
    assert schema_compatible("2.0.0") is False
    assert check_schema("2.0.0")["compatible"] is False
    assert check_schema("1.0.0")["currentVersion"] == STRATEGY_SCHEMA_VERSION


def test_migrate_preserves_unknown_fields():
    doc = {"id": "x", "name": "X", "universe": {"symbols": ["A"]},
           "someFutureField": {"keep": True}}
    out = migrate(doc, from_version="1.0.0")
    assert out["someFutureField"] == {"keep": True}
    assert out["metadata"]["schemaVersion"] == STRATEGY_SCHEMA_VERSION
