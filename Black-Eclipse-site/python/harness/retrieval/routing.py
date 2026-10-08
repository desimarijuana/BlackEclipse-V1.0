"""Route eligibility + outcome classification (Phase 7 hardening, WS4).

Before this, a source that was *skipped* (ineligible for the issuer's market, not
implemented for the data type, missing a credential) and a source that *ran and
failed* (timeout, HTTP block, parse error) both surfaced as the same coarse
"unavailable". A run could not say WHY a route was not tried, which is exactly
the distinction the international runs needed: sending TSMC/Petrobras/Samsung/SYS/
RELIANCE to SEC is INELIGIBLE, not an outage; DART without a credential is
UNCONFIGURED, not a provider failure.

`RouteCategory` is the vocabulary the planner and the receipt use. It is derived
deterministically from the source contract + request, never from a model.
"""

from __future__ import annotations

from typing import Any, Optional

from .contract import FinancialRetrievalRequest
from .sources import SourceOutcome, outcome_diagnostics

# The full, mutually-distinct set of route outcomes a receipt may report.
RouteCategory = str  # one of _CATEGORIES below

_CATEGORIES = (
    "ok",
    "ineligible",        # the provider does not cover this issuer/market (routing skip)
    "not_implemented",   # no code path exists for this data type here
    "unconfigured",      # a code path exists but its credential/base is absent
    "provider_failure",  # the provider was reached and failed (timeout/http/transport)
    "rate_limited",      # the provider is throttled (429 / cooldown / quota)
    "no_instrument",     # the issuer/ticker is not resolvable at all
    "no_data",           # the provider answered, genuinely no data for the request
    "no_matching_period",  # evidence exists but not for the requested period
    "stale_data",        # only a stale observation exists
    "invalid_document",  # fetched, but the document is not usable evidence
)

# Map a transport diagnostic category onto a route category. A parse/unsupported
# document is an INVALID DOCUMENT, not a provider outage.
_DIAGNOSTIC_TO_ROUTE = {
    "timeout": "provider_failure",
    "transport_error": "provider_failure",
    "http_error": "provider_failure",
    "blocked": "ineligible",
    "content_type_rejected": "invalid_document",
    "unsupported_document": "invalid_document",
    "javascript_only": "invalid_document",
    "paywalled": "ineligible",
    "parse_failure": "invalid_document",
    "not_configured": "unconfigured",
    "invalid_request": "no_instrument",
    "rate_limited": "rate_limited",
    "zero_results": "no_data",
}


def classify_skip(source_name: str, source: Any, request: FinancialRetrievalRequest) -> Optional[tuple[str, str]]:
    """Why `source` will not run for `request`, or None when it is available.

    Checks the provider's own eligibility contract FIRST (a non-US issuer is
    ineligible for SEC), then the data-type/config gate. The reason is preserved
    so a receipt can state it exactly — never collapsed into "unavailable".
    """
    # Provider-declared eligibility (e.g. SecFilingsSource.eligible). This is a
    # ROUTING decision: the provider is skipped, not failing.
    eligible = getattr(source, "eligible", None)
    if callable(eligible):
        try:
            if not eligible(request):
                implied = (request.market or "").strip().upper() or "the issuer's market"
                return ("ineligible", f"{source_name} does not cover issuers in {implied}")
        except Exception:  # noqa: BLE001 - an eligibility error is not a run failure
            pass

    # Data type not served by this provider.
    data_types = getattr(source, "dataTypes", ()) or ()
    if request.dataType not in data_types:
        return ("not_implemented", f"{source_name} does not implement {request.dataType}")

    # Configurable gate (bridge missing, credential missing, web disallowed).
    available = getattr(source, "available", None)
    if callable(available):
        try:
            if available(request):
                return None
        except Exception:  # noqa: BLE001
            return ("unconfigured", f"{source_name} availability could not be established")

    if not request.allowWeb and getattr(source, "name", "") == "WEB":
        return ("ineligible", "web research was disabled for this request")
    return ("unconfigured", f"{source_name} is not configured in this environment")


def classify_outcome(outcome: SourceOutcome) -> str:
    """Classify a source that ran into one route category.

    A transport diagnostic wins (timeout/http/parse); else an explicit error
    string is matched against the known absence reasons; else `provider_failure`
    for an ERROR and `no_data` for an UNAVAILABLE with no diagnostic.
    """
    if outcome.status == "OK":
        return "ok"
    # An ambiguous/unresolvable identity is a no-instrument route outcome.
    if outcome.status == "AMBIGUOUS":
        return "no_instrument"
    for diagnostic in outcome_diagnostics(outcome):
        category = str(diagnostic.get("category") or "")
        mapped = _DIAGNOSTIC_TO_ROUTE.get(category)
        if mapped:
            return mapped
    error = str(outcome.error or "").lower()
    if not error:
        return "provider_failure" if outcome.status == "ERROR" else "no_data"
    if "rate limited" in error or "429" in error:
        return "rate_limited"
    if "not in the" in error and "universe" in error:
        return "no_instrument"
    if "not_covered" in error or "not covered" in error:
        return "ineligible"
    if "not configured" in error or "requires" in error or "missing key" in error or "authentication key" in error:
        return "unconfigured"
    if "no financial statements" in error or "no data" in error or "returned no" in error or "no " in error and "in jdds" in error:
        return "no_data"
    if "timed out" in error or "timeout" in error:
        return "provider_failure"
    return "provider_failure" if outcome.status == "ERROR" else "no_data"


__all__ = ["RouteCategory", "classify_skip", "classify_outcome", "_CATEGORIES"]
