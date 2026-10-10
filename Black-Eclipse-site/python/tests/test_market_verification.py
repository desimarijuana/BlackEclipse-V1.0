"""Verification-engine tests — policies, cross-source comparison, conflicts.

Pure functions; no network, no provider, no database.
"""

from __future__ import annotations

import pytest

from harness.market.verification import (
    Observation,
    authority_of,
    independence,
    list_policies,
    policy_names,
    resolve_policy,
    verify,
    verify_series,
)


def _obs(provider: str, value: float) -> Observation:
    return Observation(provider=provider, value=value, event_time="2026-01-02T00:00:00Z")


def test_policy_names_and_resolution():
    assert set(policy_names()) == {
        "cached_fast", "fresh_preferred", "cross_verified",
        "historical_reproducible", "strict_research",
    }
    assert resolve_policy(None).name == "fresh_preferred"
    assert resolve_policy("STRICT_RESEARCH").name == "strict_research"
    with pytest.raises(ValueError):
        resolve_policy("no_such_policy")


def test_policy_flags_are_documented():
    cross = resolve_policy("cross_verified")
    assert cross.require_verification is True
    assert cross.min_sources == 2
    assert cross.allow_single_source is False
    strict = resolve_policy("strict_research")
    assert strict.fail_on_material_conflict is True
    assert strict.require_authoritative is True
    cached = resolve_policy("cached_fast")
    assert cached.require_verification is False
    assert cached.allow_single_source is True


def test_authority_and_independence():
    assert authority_of("sec") > authority_of("yahoo")
    assert independence("yahoo", "stooq") == "established"
    assert independence("yahoo", "yahoo") == "shared"
    assert independence("yahoo", "some_unknown_feed") == "unknown"


def test_verify_agreement_is_verified():
    out = verify(
        [_obs("yahoo", 100.0), _obs("stooq", 100.1)],
        capability="quote", policy="cross_verified", tolerance=0.015,
    )
    assert out.status == "verified"
    assert out.verified is True
    assert out.independent_sources == 2
    assert out.conflicts == []
    assert out.scorecard["verificationCoverage"] == 1.0


def test_verify_disagreement_is_conflicted_not_averaged():
    out = verify(
        [_obs("yahoo", 100.0), _obs("stooq", 120.0)],
        capability="quote", policy="cross_verified", tolerance=0.015,
    )
    assert out.status == "conflicted"
    assert out.verified is False
    assert len(out.conflicts) == 1
    assert out.conflicts[0]["maxRelativeDiff"] > 0.015
    assert out.conflicts[0]["category"] == "value_mismatch"


def test_strict_research_fails_on_conflict():
    out = verify(
        [_obs("yahoo", 100.0), _obs("stooq", 120.0)],
        capability="quote", policy="strict_research", tolerance=0.015,
    )
    assert out.status == "failed"
    assert out.verified is False


def test_shared_upstream_is_classified_distinctly():
    out = verify(
        [_obs("treasury", 4.2), _obs("fred", 4.8)],
        capability="bonds", policy="cross_verified", tolerance=0.01,
    )
    assert out.status == "conflicted"
    assert out.conflicts[0]["category"] == "shared_upstream_divergence"


def test_single_source_behaviour_depends_on_policy():
    cross = verify([_obs("yahoo", 100.0)], capability="quote", policy="cross_verified")
    assert cross.status == "unverified"
    assert cross.verified is False
    fresh = verify([_obs("yahoo", 100.0)], capability="quote", policy="fresh_preferred")
    assert fresh.status == "verified"
    assert fresh.verified is True


def test_no_usable_observations_fails_strict():
    out = verify([Observation(provider="yahoo", value=None)],
                 capability="quote", policy="strict_research")
    assert out.status == "failed"
    assert out.verified is False


def test_verify_series_agreement_and_disagreement():
    a = [("2026-01-02T00:00:00Z", 100.0), ("2026-01-03T00:00:00Z", 101.0), ("2026-01-04T00:00:00Z", 102.0)]
    b = [("2026-01-02T00:00:00Z", 100.1), ("2026-01-03T00:00:00Z", 101.1), ("2026-01-04T00:00:00Z", 102.1)]
    good = verify_series({"yahoo": a, "stooq": b}, policy="cross_verified", tolerance=0.015)
    assert good.status == "verified"
    assert good.verified is True

    c = [("2026-01-02T00:00:00Z", 100.0), ("2026-01-03T00:00:00Z", 101.0), ("2026-01-04T00:00:00Z", 150.0)]
    bad = verify_series({"yahoo": a, "stooq": c}, policy="cross_verified", tolerance=0.015)
    assert bad.status == "conflicted"
    assert bad.conflicts


def test_verify_series_no_overlap_is_unverified():
    a = [("2026-01-02T00:00:00Z", 100.0)]
    b = [("2026-02-02T00:00:00Z", 100.1)]
    out = verify_series({"yahoo": a, "stooq": b}, policy="cross_verified")
    assert out.status == "unverified"


def test_list_policies_serializable():
    rows = list_policies()
    assert len(rows) == 5
    assert all("description" in r and "minSources" in r for r in rows)
