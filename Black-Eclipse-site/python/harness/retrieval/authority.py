"""Source authority and freshness arbitration (Phase 13, ADR-H115/H116).

One ordering table and one decision function. Before this module the source
ordering and the first-success rule lived elsewhere, and the vault was first for
every price-shaped type so the live provider was never consulted once it
answered. This module replaces both with a single, testable authority:

  * ``AUTHORITY`` — one row per ``DataType``: the ordered candidate list, whether
    the type is ``single_best`` (first success) or ``arbitrated`` (run the
    candidates, resolve, preserve disagreement), and the freshness ceiling for
    the type.
  * ``decide_source`` — a PURE function. Given the authority, the outcomes that
    ran, and the request, it returns the chosen source, a plain reason, and every
    rejected candidate with why. A candidate that did not run is *skipped*, not a
    rejection.

No I/O. This module imports no orchestrator. ``detect_conflicts`` and
``tier_rank`` are reused verbatim — there is no second conflict algorithm.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from .conflicts import detect_conflicts
from .contract import FinancialRetrievalRequest, NormalizedFinancialObject
from .policies import format_age, max_age_seconds, tier_rank
from .sources import SourceOutcome

# Provider names are opaque ids here; the layer maps them to source instances.
# Defined HERE (not in planner) so `authority` has no import cycle with planner;
# `planner` re-exports these names for backwards compatibility.
STRUCTURED_VAULT = "JDDS"
STRUCTURED_LIVE = "LIVE_STRUCTURED"
SEC_FILINGS = "SEC"
WEB = "WEB"
CRYPTO = "CRYPTO"

SourcePolicy = Literal["single_best", "arbitrated"]


@dataclass(frozen=True)
class DataTypeAuthority:
    """The authority for one data type. One row per ``DataType``."""

    data_type: str
    candidates: tuple[str, ...]   # ordered preference, strongest first
    policy: SourcePolicy
    require_precise: bool          # web may never satisfy it
    web_allowed: bool
    request_window_s: int          # the freshness ceiling for THIS type


# The ONE ordering table. A new data type gets exactly one row here.
AUTHORITY: dict[str, DataTypeAuthority] = {
    # A current price is arbitrated: a fresh live reading must be able to beat a
    # saved snapshot, and a disagreement between the two must be shown.
    "current_quote": DataTypeAuthority(
        "current_quote", (STRUCTURED_LIVE, STRUCTURED_VAULT, WEB),
        "arbitrated", require_precise=True, web_allowed=True,
        request_window_s=900,          # 15 min: fresher than a saved snapshot
    ),
    # A history series: live provider first (it carries the real series), the
    # snapshot second as an honest fallback with its age stated.
    "historical_prices": DataTypeAuthority(
        "historical_prices", (STRUCTURED_LIVE, STRUCTURED_VAULT),
        "arbitrated", require_precise=True, web_allowed=False,
        request_window_s=6 * 3600,
    ),
    "macro_series": DataTypeAuthority(
        "macro_series", (STRUCTURED_LIVE, STRUCTURED_VAULT),
        "arbitrated", require_precise=True, web_allowed=False,
        request_window_s=12 * 3600,
    ),
    "company_profile": DataTypeAuthority(
        "company_profile", (STRUCTURED_LIVE, STRUCTURED_VAULT, WEB),
        "arbitrated", require_precise=False, web_allowed=True,
        request_window_s=24 * 3600,
    ),
    # Statements stay single-best: an issuer filing is not a race with a snapshot.
    "financial_statements": DataTypeAuthority(
        "financial_statements", (SEC_FILINGS, STRUCTURED_VAULT, WEB),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=400 * 24 * 3600,
    ),
    # Qualitative / web-first types: the web is the first-success source.
    "earnings": DataTypeAuthority(
        "earnings", (WEB, STRUCTURED_VAULT),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=95 * 24 * 3600,
    ),
    "news": DataTypeAuthority(
        "news", (WEB,),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=24 * 3600,
    ),
    "web_research": DataTypeAuthority(
        "web_research", (WEB,),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=24 * 3600,
    ),
    "world_events": DataTypeAuthority(
        "world_events", (WEB,),
        "single_best", require_precise=False, web_allowed=True,
        request_window_s=24 * 3600,
    ),
    # A calculation needs structured inputs; web is forbidden for it.
    "derived_metric": DataTypeAuthority(
        "derived_metric", (STRUCTURED_VAULT, STRUCTURED_LIVE),
        "single_best", require_precise=True, web_allowed=False,
        request_window_s=6 * 3600,
    ),
}

# A data type absent from the table has no specific policy; web research is the
# honest default, exactly as the old static order used to default.
_DEFAULT = DataTypeAuthority(
    "unknown", (WEB,), "single_best", require_precise=False, web_allowed=True,
    request_window_s=24 * 3600,
)


def authority_for(data_type: str) -> DataTypeAuthority:
    """The authority row for a data type, or the web-research default."""
    return AUTHORITY.get(data_type, _DEFAULT)


def effective_authority(
    authority: DataTypeAuthority, request: FinancialRetrievalRequest
) -> DataTypeAuthority:
    """The authority actually used for a request, crypto-aware.

    A crypto request is owned by the dedicated CRYPTO source; the vault/live
    provider cannot price a crypto pair. Prepending CRYPTO here (for a crypto
    request only) keeps the static ``AUTHORITY`` table stable for every other
    instrument while letting ``decide_source`` consider the crypto candidate.
    """
    if authority.data_type not in ("current_quote", "historical_prices"):
        return authority
    # Import locally: `structured` reaches `..tools`, which must not be imported
    # at `authority` module load time.
    from .structured import is_crypto  # noqa: PLC0415

    if not is_crypto(request):
        return authority
    if CRYPTO in authority.candidates:
        return authority
    return DataTypeAuthority(
        authority.data_type,
        (CRYPTO, *authority.candidates),
        authority.policy,
        authority.require_precise,
        authority.web_allowed,
        authority.request_window_s,
    )


@dataclass(frozen=True)
class SourceDecision:
    """The result of ``decide_source``. Pure data, safe to surface behind details."""

    chosen: Optional[str]
    reason: str                        # a sentence, safe to show behind "details"
    rejected: list[tuple[str, str]]    # (source, why it did not answer)


def _observation(outcome: SourceOutcome) -> tuple[Optional[str], str]:
    """The newest observation time and its source, across an outcome's objects."""
    times: list[str] = []
    sources: set[str] = set()
    for obj in outcome.objects:
        stamp = obj.observation_time or obj.dataTimestamp
        if stamp:
            times.append(str(stamp))
        sources.add(str(getattr(obj, "observation_source", "unknown") or "unknown"))
    newest = max(times) if times else None
    if "provider_asof" in sources:
        return newest, "provider_asof"
    if "snapshot_write" in sources:
        return newest, "snapshot_write"
    return newest, "unknown"


def _age_seconds(ts: Optional[str], *, now: Optional[float]) -> Optional[float]:
    if not ts:
        return None
    import datetime as _dt

    text = str(ts).strip().replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    ref = _dt.datetime.now(_dt.timezone.utc) if now is None else _dt.datetime.fromtimestamp(
        now, _dt.timezone.utc
    )
    return (ref - parsed).total_seconds()


def _is_stale(outcome: SourceOutcome, authority: DataTypeAuthority, request: FinancialRetrievalRequest, now: Optional[float]) -> Optional[str]:
    """A stale reason for one outcome, or None when it may answer.

    The effective window is the stricter of the type's own ceiling and the
    caller's freshness window. An undateable candidate cannot be proven stale and
    is therefore eligible — a missing time is not a fabrication.
    """
    newest, _source = _observation(outcome)
    age = _age_seconds(newest, now=now)
    if age is None:
        return None
    request_window = max_age_seconds(request.freshnessRequirement)
    window = min(authority.request_window_s, request_window)
    if window <= 0:
        window = authority.request_window_s
    if age > window:
        return (
            f"STALE_SOURCE: {outcome.source} newest observation is {format_age(age)} old "
            f"(freshness requirement '{request.freshnessRequirement}' allows {format_age(window)})"
        )
    return None


def _numeric_groups(objects: list[NormalizedFinancialObject]) -> dict[str, list[NormalizedFinancialObject]]:
    """Group numeric observations OF THE SAME FACT (name@timestamp@period).

    Mirrors the keying the layer uses so a cross-source disagreement is detected
    by the SAME rule. Non-numeric facts cannot disagree numerically and are not
    grouped.
    """
    groups: dict[str, list[NormalizedFinancialObject]] = {}
    for obj in objects:
        if isinstance(obj.value, (int, float)) and not isinstance(obj.value, bool):
            key = f"{obj.name}@{obj.dataTimestamp or ''}@{obj.period or ''}"
            groups.setdefault(key, []).append(obj)
    return groups


def _newest(objects: list[NormalizedFinancialObject]) -> str:
    stamps = [str(o.observation_time or o.dataTimestamp) for o in objects if (o.observation_time or o.dataTimestamp)]
    return max(stamps) if stamps else ""


def decide_source(
    authority: DataTypeAuthority,
    outcomes: list[SourceOutcome],
    request: FinancialRetrievalRequest,
    *,
    now: Optional[float] = None,
) -> SourceDecision:
    """Choose which eligible source answers, preserving the disagreement.

    Rules, in order:
      1. A candidate that did not run is skipped, not a rejection.
      2. Web is rejected when the type forbids it (``web_allowed`` False; the
         precise types).
      3. A candidate whose newest observation is older than the effective window
         is rejected with ``STALE_SOURCE`` and the measured age in the reason.
      4. Among survivors the existing ``detect_conflicts`` decides: agreement →
         the highest-tier newest value; disagreement → no chosen value.
    """
    all_outcomes: dict[str, SourceOutcome] = {o.source: o for o in outcomes}
    rejected: list[tuple[str, str]] = []
    survivors: list[str] = []

    for name in authority.candidates:
        if name == WEB and not authority.web_allowed:
            rejected.append((name, "WEB is not eligible for a precise data type"))
            continue
        outcome = all_outcomes.get(name)
        if outcome is None:
            # Rule 1: a candidate that did not run is skipped, not a rejection.
            rejected.append((name, "skipped: the candidate did not run"))
            continue
        if outcome.status != "OK" or not (outcome.objects or outcome.evidence):
            # It ran and failed / returned nothing — record WHY, with its error.
            detail = outcome.error or f"{name} returned no data"
            rejected.append((name, f"{name} ran but did not answer: {detail}"))
            continue
        stale = _is_stale(outcome, authority, request, now)
        if stale is not None:
            rejected.append((name, stale))
            continue
        survivors.append(name)

    # A precise type rejects web even when it is not a listed candidate for the
    # type (the prohibition is a property of the type, not of the table row).
    if not authority.web_allowed and not any(name == WEB for name, _why in rejected):
        rejected.append((WEB, "WEB is not eligible for a precise data type"))

    if not survivors:
        had_stale = any("STALE_SOURCE" in why for _name, why in rejected)
        code = "NO_FRESH_SOURCE" if had_stale else "UNAVAILABLE"
        reason = (
            f"{code}: no eligible source answered within the freshness window"
            if had_stale
            else "UNAVAILABLE: no eligible source answered"
        )
        return SourceDecision(None, reason, rejected)

    combined: list[NormalizedFinancialObject] = []
    for name in survivors:
        combined.extend(all_outcomes[name].objects)
    _chosen, _warnings, unresolved = detect_conflicts(_numeric_groups(combined))
    if unresolved:
        return SourceDecision(
            None,
            "CONFLICTING: the eligible sources disagree beyond the tolerance",
            rejected,
        )

    def rank(name: str) -> tuple[int, str]:
        outcome = all_outcomes[name]
        tier = max(
            (tier_rank(o.source.sourceType) for o in outcome.objects),
            default=0,
        )
        return (tier, _newest(outcome.objects))

    chosen = max(survivors, key=rank)
    return SourceDecision(chosen, "sources agree", rejected)


__all__ = [
    "AUTHORITY",
    "DataTypeAuthority",
    "SourceDecision",
    "SourcePolicy",
    "STRUCTURED_VAULT",
    "STRUCTURED_LIVE",
    "SEC_FILINGS",
    "WEB",
    "CRYPTO",
    "authority_for",
    "effective_authority",
    "decide_source",
]
