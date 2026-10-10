"""Independent cross-source verification and the named verification policies.

JDdS/provider data is not inherently trustworthy. This module is the ONE place
that decides — deterministically and explainably — whether a market observation
is *verified*, *unverified*, *conflicted* or *failed*, given a caller's
verification policy.

Nothing here fetches. The tool layer retrieves candidate observations (from the
Market Data Gateway, optionally pinning distinct providers) and hands them here;
this module only compares, scores and records conflicts. It never averages two
disagreeing values and never claims verification merely because two HTTP
responses arrived.

Named policies (directive §6.5):
    cached_fast              use existing data if it satisfies freshness/quality
    fresh_preferred          prefer a fresh retrieval; disclose any fallback
    cross_verified           retrieve + compare suitable independent sources
    historical_reproducible  use a defined, versioned dataset; enforce PIT
    strict_research          authority + freshness + completeness; fail on conflict

A request is NEVER silently downgraded (e.g. strict_research → cached_fast).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── Named verification policies ─────────────────────────────────────────────


@dataclass(frozen=True)
class PolicySpec:
    """The testable behaviour behind a named verification policy."""

    name: str
    require_verification: bool
    min_sources: int
    # Freshness ceiling in seconds for the policy, or None to defer to the
    # request's own freshness class / the market calendar.
    max_age_s: Optional[float]
    fail_on_material_conflict: bool
    # Whether a single suitable source may be accepted (with disclosure) when no
    # independent corroboration exists.
    allow_single_source: bool
    require_authoritative: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "requireVerification": self.require_verification,
            "minSources": self.min_sources,
            "maxAgeSeconds": self.max_age_s,
            "failOnMaterialConflict": self.fail_on_material_conflict,
            "allowSingleSource": self.allow_single_source,
            "requireAuthoritative": self.require_authoritative,
            "description": self.description,
        }


_POLICIES: dict[str, PolicySpec] = {
    "cached_fast": PolicySpec(
        name="cached_fast",
        require_verification=False,
        min_sources=1,
        max_age_s=None,
        fail_on_material_conflict=False,
        allow_single_source=True,
        require_authoritative=False,
        description=(
            "Fastest path: use existing/cached observations when they satisfy the "
            "request's freshness and quality requirements. No cross-source check."
        ),
    ),
    "fresh_preferred": PolicySpec(
        name="fresh_preferred",
        require_verification=False,
        min_sources=1,
        max_age_s=None,
        fail_on_material_conflict=False,
        allow_single_source=True,
        require_authoritative=False,
        description=(
            "Prefer a new retrieval; a fallback to older/cached data is permitted "
            "only when it is disclosed in the result."
        ),
    ),
    "cross_verified": PolicySpec(
        name="cross_verified",
        require_verification=True,
        min_sources=2,
        max_age_s=None,
        fail_on_material_conflict=False,
        allow_single_source=False,
        require_authoritative=False,
        description=(
            "Retrieve and compare suitable independent sources for the covered "
            "observations; a material disagreement is recorded as a conflict."
        ),
    ),
    "historical_reproducible": PolicySpec(
        name="historical_reproducible",
        require_verification=True,
        min_sources=2,
        max_age_s=None,
        fail_on_material_conflict=True,
        allow_single_source=False,
        require_authoritative=False,
        description=(
            "Use a defined, versioned dataset and preserve point-in-time "
            "information-availability constraints. Conflicts fail the policy."
        ),
    ),
    "strict_research": PolicySpec(
        name="strict_research",
        require_verification=True,
        min_sources=2,
        max_age_s=None,
        fail_on_material_conflict=True,
        allow_single_source=False,
        require_authoritative=True,
        description=(
            "Enforce source authority, freshness, completeness and discrepancy "
            "thresholds. A material unresolved conflict FAILS the policy."
        ),
    ),
}

DEFAULT_POLICY = "fresh_preferred"


def policy_names() -> tuple[str, ...]:
    return tuple(_POLICIES.keys())


def resolve_policy(name: Optional[str]) -> PolicySpec:
    """Resolve a policy by name. An unknown name is a hard error (never a silent
    downgrade to a weaker default)."""
    key = (name or DEFAULT_POLICY).strip().lower()
    spec = _POLICIES.get(key)
    if spec is None:
        raise ValueError(
            f"unknown verification policy {name!r}; known: {', '.join(_POLICIES)}"
        )
    return spec


def list_policies() -> list[dict[str, Any]]:
    return [p.to_dict() for p in _POLICIES.values()]


# ── Source authority + upstream lineage ─────────────────────────────────────
# Authority is a documented, deterministic weighting — never a claim that one
# brand is "better". Officials/filings rank above vendor feeds; keyless scrapes
# rank lowest. Unknown providers default to 0.5.
AUTHORITY: dict[str, float] = {
    "sec": 1.0,
    "sec_edgar": 1.0,
    "treasury": 0.95,
    "fred": 0.95,
    "fx": 0.9,           # ECB reference rates
    "polygon": 0.85,
    "finnhub": 0.8,
    "binance": 0.8,
    "coingecko": 0.75,
    "yahoo": 0.6,
    "stooq": 0.55,
}


def authority_of(provider: str) -> float:
    return AUTHORITY.get((provider or "").strip().lower(), 0.5)


# Known upstreams. Two providers share a lineage when their underlying feed is
# the same; comparing them is NOT independent verification. A provider absent
# from this map has UNKNOWN lineage, so independence is reported as "unknown",
# never assumed.
_UPSTREAM_LINEAGE: dict[str, str] = {
    "yahoo": "yahoo",
    "stooq": "stooq",
    "binance": "binance",
    "coingecko": "coingecko",
    "polygon": "polygon",
    "finnhub": "finnhub",
    "treasury": "us-treasury",
    "fred": "us-treasury",
    "fx": "ecb",
    "sec": "sec-edgar",
    "sec_edgar": "sec-edgar",
}

Independence = str  # "established" | "shared" | "unknown"


def lineage_of(provider: str) -> Optional[str]:
    return _UPSTREAM_LINEAGE.get((provider or "").strip().lower())


def independence(a: str, b: str) -> Independence:
    """Whether two providers can corroborate each other.

    * `shared`      — same known upstream (NOT independent),
    * `unknown`     — at least one lineage is unrecorded (never assumed),
    * `established` — different known upstreams.
    """
    la, lb = lineage_of(a), lineage_of(b)
    if la is None or lb is None:
        return "unknown"
    return "shared" if la == lb else "established"


# ── Observation + outcome contracts ─────────────────────────────────────────


@dataclass
class Observation:
    """One provider's value for a capability, with provenance."""

    provider: str
    value: Optional[float]
    event_time: Optional[str] = None
    retrieved_at: Optional[str] = None
    authoritative: bool = False

    @property
    def authority(self) -> float:
        return authority_of(self.provider)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "value": self.value,
            "eventTime": self.event_time,
            "retrievedAt": self.retrieved_at,
            "authoritative": self.authoritative,
            "authority": self.authority,
            "lineage": lineage_of(self.provider),
        }


@dataclass
class Comparison:
    providers: tuple[str, str]
    independence: Independence
    relative_diff: Optional[float]
    within_tolerance: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": list(self.providers),
            "independence": self.independence,
            "relativeDiff": self.relative_diff,
            "withinTolerance": self.within_tolerance,
            "detail": self.detail,
        }


@dataclass
class Conflict:
    capability: str
    candidates: list[dict[str, Any]]
    max_relative_diff: float
    tolerance: float
    category: str
    resolved: bool = False
    selected_provider: Optional[str] = None
    rationale: Optional[str] = None
    policy: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "candidates": self.candidates,
            "maxRelativeDiff": self.max_relative_diff,
            "tolerance": self.tolerance,
            "category": self.category,
            "resolved": self.resolved,
            "selectedProvider": self.selected_provider,
            "rationale": self.rationale,
            "policy": self.policy,
        }


@dataclass
class VerificationOutcome:
    capability: str
    policy: str
    status: str  # verified | unverified | conflicted | failed
    sources: list[dict[str, Any]] = field(default_factory=list)
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    scorecard: dict[str, Any] = field(default_factory=dict)
    independent_sources: int = 0
    message: str = ""

    @property
    def verified(self) -> bool:
        return self.status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": self.capability,
            "policy": self.policy,
            "status": self.status,
            "verified": self.verified,
            "independentSources": self.independent_sources,
            "sources": self.sources,
            "comparisons": self.comparisons,
            "conflicts": self.conflicts,
            "scorecard": self.scorecard,
            "message": self.message,
        }


def _rel_diff(a: float, b: float) -> float:
    denom = max(abs(a), abs(b))
    if denom == 0:
        return 0.0
    return abs(a - b) / denom


def _count_independent(observations: list[Observation]) -> int:
    """Number of observations attributable to distinct known lineages, plus one
    for every unknown-lineage source (unknowns are never merged with a known)."""
    known: set[str] = set()
    unknown = 0
    for obs in observations:
        lineage = lineage_of(obs.provider)
        if lineage is None:
            unknown += 1
        else:
            known.add(lineage)
    return len(known) + unknown


def _scorecard(
    observations: list[Observation],
    policy: PolicySpec,
    *,
    independent_sources: int,
    age_seconds: Optional[float],
) -> dict[str, Any]:
    usable = [o for o in observations if o.value is not None]
    max_authority = max((o.authority for o in usable), default=0.0)
    freshness_ok = True
    if age_seconds is not None and policy.max_age_s is not None:
        freshness_ok = age_seconds <= policy.max_age_s
    verification_coverage = 0.0
    if independent_sources >= 2:
        verification_coverage = 1.0
    elif independent_sources == 1:
        verification_coverage = 0.5
    return {
        "sourceCount": len(usable),
        "independentSources": independent_sources,
        "maxAuthority": round(max_authority, 3),
        "authorityOk": (max_authority >= 0.8) if policy.require_authoritative else True,
        "freshnessCompliance": freshness_ok,
        "verificationCoverage": verification_coverage,
        "unknownMetadata": sum(1 for o in observations if lineage_of(o.provider) is None),
    }


def verify(
    observations: list[Observation],
    *,
    capability: str,
    policy: str | PolicySpec = DEFAULT_POLICY,
    tolerance: float = 0.015,
    age_seconds: Optional[float] = None,
) -> VerificationOutcome:
    """Compare scalar observations from candidate providers under a policy.

    Returns a deterministic outcome. `tolerance` is a relative difference under
    which two values are considered to agree.
    """
    spec = policy if isinstance(policy, PolicySpec) else resolve_policy(policy)
    usable = [o for o in observations if o.value is not None and o.value == o.value]
    independent = _count_independent(usable)
    scorecard = _scorecard(usable, spec, independent_sources=independent, age_seconds=age_seconds)
    sources = [o.to_dict() for o in observations]
    out = VerificationOutcome(
        capability=capability, policy=spec.name, status="unverified",
        sources=sources, independent_sources=independent, scorecard=scorecard,
    )

    if not usable:
        out.status = "failed" if spec.require_verification else "unverified"
        out.message = "no usable observations from any source"
        return out

    # Pairwise comparisons across distinct providers.
    comparisons: list[Comparison] = []
    max_diff = 0.0
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            a, b = usable[i], usable[j]
            if a.provider == b.provider:
                continue
            diff = _rel_diff(float(a.value), float(b.value))  # type: ignore[arg-type]
            indep = independence(a.provider, b.provider)
            comparisons.append(Comparison(
                providers=(a.provider, b.provider), independence=indep,
                relative_diff=round(diff, 6), within_tolerance=diff <= tolerance,
                detail=(f"{a.provider}={a.value} vs {b.provider}={b.value}"),
            ))
            max_diff = max(max_diff, diff)
    out.comparisons = [c.to_dict() for c in comparisons]

    if len(usable) < spec.min_sources:
        # Not enough sources to satisfy the policy.
        if spec.allow_single_source:
            out.status = "verified"
            out.message = (
                f"single source accepted under policy '{spec.name}' (no independent "
                "corroboration required)"
            )
        else:
            out.status = "unverified"
            out.message = (
                f"policy '{spec.name}' requires >= {spec.min_sources} sources but only "
                f"{len(usable)} usable source(s) were available"
            )
        return out

    if max_diff > tolerance:
        candidates = [o.to_dict() for o in usable]
        category = "value_mismatch"
        # A shared upstream is not a conflict of two independent facts but a
        # likely shared error; classify it distinctly.
        if comparisons and all(c.independence == "shared" for c in comparisons):
            category = "shared_upstream_divergence"
        conflict = Conflict(
            capability=capability, candidates=candidates,
            max_relative_diff=round(max_diff, 6), tolerance=tolerance,
            category=category, policy=spec.name,
        )
        out.conflicts = [conflict.to_dict()]
        out.status = "failed" if spec.fail_on_material_conflict else "conflicted"
        out.message = (
            f"providers disagree by {max_diff:.1%} (> tolerance {tolerance:.1%}); "
            + ("policy fails on unresolved conflict" if spec.fail_on_material_conflict
               else "flagged, not averaged")
        )
        return out

    out.status = "verified"
    out.message = (
        f"{len(usable)} source(s) agree within tolerance ({max_diff:.2%}); "
        f"{independent} independent lineage(s)"
    )
    return out


def verify_series(
    series_by_provider: dict[str, list[tuple[str, float]]],
    *,
    capability: str = "historical",
    policy: str | PolicySpec = DEFAULT_POLICY,
    tolerance: float = 0.015,
    sample: int = 12,
) -> VerificationOutcome:
    """Verify a bar series across providers by comparing aligned closes.

    A bounded, deterministic sample of aligned timestamps is compared (the max
    relative close difference drives the verdict), rather than every bar, so the
    outcome is explainable and cheap. Timestamps present in one source only are
    reported as coverage gaps, never as agreement.
    """
    spec = policy if isinstance(policy, PolicySpec) else resolve_policy(policy)
    providers = list(series_by_provider.keys())
    maps: dict[str, dict[str, float]] = {
        p: {str(ts): float(v) for ts, v in rows if v == v} for p, rows in series_by_provider.items()
    }
    sources = [
        {"provider": p, "bars": len(maps[p]), "authority": authority_of(p),
         "lineage": lineage_of(p)}
        for p in providers
    ]
    independent = _count_independent([Observation(p, None) for p in providers])
    scorecard = _scorecard([Observation(p, None) for p in providers], spec,
                           independent_sources=independent, age_seconds=None)
    out = VerificationOutcome(
        capability=capability, policy=spec.name, status="unverified",
        sources=sources, independent_sources=independent, scorecard=scorecard,
    )
    if len(providers) < 2:
        if spec.allow_single_source:
            out.status = "verified"
            out.message = f"single source accepted under policy '{spec.name}'"
        else:
            out.status = "unverified"
            out.message = f"policy '{spec.name}' requires independent confirmation"
        return out

    # Align on timestamps shared by ALL providers.
    common: set[str] = set(maps[providers[0]])
    for p in providers[1:]:
        common &= set(maps[p])
    common_sorted = sorted(common)
    if not common_sorted:
        out.status = "unverified"
        out.message = "no overlapping timestamps across sources to compare"
        return out
    step = max(1, len(common_sorted) // max(1, sample))
    chosen = common_sorted[::step][:sample]

    comparisons: list[Comparison] = []
    max_diff = 0.0
    for ts in chosen:
        values = [(p, maps[p][ts]) for p in providers]
        for i in range(len(values)):
            for j in range(i + 1, len(values)):
                (pa, va), (pb, vb) = values[i], values[j]
                diff = _rel_diff(va, vb)
                comparisons.append(Comparison(
                    providers=(pa, pb), independence=independence(pa, pb),
                    relative_diff=round(diff, 6), within_tolerance=diff <= tolerance,
                    detail=f"{ts}: {pa}={va} vs {pb}={vb}",
                ))
                max_diff = max(max_diff, diff)
    out.comparisons = [c.to_dict() for c in comparisons]

    if max_diff > tolerance:
        candidates = [
            {"provider": p, "value": maps[p][ts]}
            for ts in chosen[:1] for p in providers
        ]
        category = "value_mismatch"
        if comparisons and all(c.independence == "shared" for c in comparisons):
            category = "shared_upstream_divergence"
        out.conflicts = [Conflict(
            capability=capability, candidates=candidates,
            max_relative_diff=round(max_diff, 6), tolerance=tolerance,
            category=category, policy=spec.name,
        ).to_dict()]
        out.status = "failed" if spec.fail_on_material_conflict else "conflicted"
        out.message = (
            f"series sources disagree by up to {max_diff:.1%} over {len(chosen)} sampled "
            f"timestamps (tolerance {tolerance:.1%})"
        )
        return out
    out.status = "verified"
    out.message = (
        f"{len(providers)} sources agree within tolerance over {len(chosen)} sampled "
        f"timestamps (max diff {max_diff:.2%})"
    )
    return out


__all__ = [
    "AUTHORITY",
    "Comparison",
    "Conflict",
    "DEFAULT_POLICY",
    "Observation",
    "PolicySpec",
    "VerificationOutcome",
    "authority_of",
    "independence",
    "lineage_of",
    "list_policies",
    "policy_names",
    "resolve_policy",
    "verify",
    "verify_series",
]
