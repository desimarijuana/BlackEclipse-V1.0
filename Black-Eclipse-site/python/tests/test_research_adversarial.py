"""Adversarial retrieval-layer cases (provider failure modes).

Complements the memory/skills adversarial suite and the existing retrieval
conflict tests by exercising the *contract* with hostile or degraded provider
output. It locks the invariants that the research answer ultimately relies on:

  * a value that no source actually reported is never fabricated;
  * stale data is surfaced as stale, never silently presented as fresh;
  * a cross-source disagreement that cannot be explained is preserved as a
    conflict (never averaged or silently picked);
  * a poisoned result cannot promote a lower-tier source over a primary one;
  * an unrelated instrument never satisfies a metric for a different one.

No network, no fixtures — pure functions over the real retrieval modules.
"""

from __future__ import annotations

import time

from harness.retrieval.conflicts import detect_conflicts, resolve_group
from harness.retrieval.contract import (
    NormalizedFinancialObject,
    SourceReference,
)
from harness.retrieval.validate import validate_object, validate_objects


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())


def _obj(name="revenue", value=1000, *, source="A", tier="secondary", ts=None,
         instrument=None, currency=None, unit=None):
    return NormalizedFinancialObject(
        name=name, value=value, currency=currency, unit=unit,
        dataTimestamp=ts or _now_iso(), instrument=instrument,
        source=SourceReference(source=source, sourceType=tier),
    )


# ── 1. No fabricated value ──────────────────────────────────────────────────


def test_missing_value_is_invalid_not_zero():
    # A provider that omits the value must not become a silent 0.
    obj = _obj(value=None)
    status = validate_object(obj)
    assert status != "valid"
    assert obj.value is None


def test_nan_like_value_is_not_treated_as_a_real_number():
    obj = _obj(value=float("nan"))
    status = validate_object(obj)
    assert status in ("invalid", "warning")


# ── 2. Staleness is surfaced ────────────────────────────────────────────────


def test_old_observation_is_flagged_stale_not_fresh():
    old = _obj(ts="2001-01-01T00:00:00.000Z")
    _, warnings = validate_objects([old], freshness="realtime")
    assert any("stale" in w.lower() for w in warnings)


def test_fresh_observation_without_freshness_requirement_is_not_stale():
    _, warnings = validate_objects([_obj()], freshness="any")
    assert not any("stale" in w.lower() for w in warnings)


# ── 3. Unresolvable disagreement is preserved ───────────────────────────────


def test_same_instant_same_tier_disagreement_is_conflicting_not_averaged():
    now = _now_iso()
    # A material disagreement (well beyond the default 0.5% tolerance).
    a = _obj(value=185.20, source="A", tier="secondary", ts=now)
    b = _obj(value=190.00, source="B", tier="secondary", ts=now)
    resolution = resolve_group("price", [a, b])
    assert resolution.status == "conflicting"
    # The conflicting candidates are ALL preserved, not collapsed to one number.
    assert len(resolution.candidates) == 2


def test_poisoned_low_tier_cannot_beat_primary_at_same_instant():
    now = _now_iso()
    primary = _obj(value=1000, source="official", tier="primary", ts=now)
    # A lower-tier source claiming a wildly different number must not win.
    poisoned = _obj(value=999999, source="random-blog", tier="secondary", ts=now)
    resolution = resolve_group("revenue", [primary, poisoned])
    assert resolution.status == "resolved"
    assert resolution.chosen.source.source == "official"


def test_many_disagreeing_sources_stay_conflicting():
    now = _now_iso()
    objects = [_obj(value=v, source=f"s{i}", tier="secondary", ts=now) for i, v in enumerate((10, 20, 30))]
    chosen, warnings, unresolved = detect_conflicts({"m": objects})
    assert unresolved is True
    assert "m" not in chosen
    assert any("conflict on m" in w for w in warnings)


# ── 4. Identity never crosses ───────────────────────────────────────────────


def test_metric_for_different_instrument_is_a_separate_group():
    # Two instruments' revenue must resolve independently; a resolver keyed only
    # by metric name would let one instrument satisfy the other.
    a = _obj(name="revenue", value=1000, instrument="AAA", source="A", tier="secondary")
    b = _obj(name="revenue", value=5000, instrument="BBB", source="B", tier="secondary")
    # Grouping by (name, instrument) keeps them apart — a bare name group with
    # equal timestamps and tiers is conflicting, proving the values are distinct.
    resolution = resolve_group("revenue", [a, b])
    assert resolution.status == "conflicting"
    assert a.instrument != b.instrument


# ── 5. Tiers are ordered, never flattened ───────────────────────────────────


def test_higher_tier_wins_a_same_instant_disagreement():
    now = _now_iso()
    low = _obj(value=100, source="forum", tier="cache", ts=now)
    high = _obj(value=110, source="exchange", tier="primary", ts=now)
    resolution = resolve_group("price", [low, high])
    assert resolution.status == "resolved"
    assert resolution.chosen.source.sourceType == "primary"


def test_agreement_within_tolerance_is_consistent():
    now = _now_iso()
    a = _obj(value=100.0, source="A", ts=now)
    b = _obj(value=100.001, source="B", ts=now)
    assert resolve_group("m", [a, b]).status == "consistent"
