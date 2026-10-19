"""The declared acquisition-source registry — DATA, one row per source.

A source that has no row here is not collectable. Every row declares its label,
the capability it reaches on the read-only bridge, the CLOSED parameter set the
tool may pass, its rate ceiling, its per-call row ceiling, its licence and its
attribution, and the exact CSV columns its rows carry. `registry_issues()`
fails a row that is incomplete, so adding a source without a licence (or with
an open parameter set) is a test failure, not a silent gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AcquisitionSource:
    """One declared bulk source. Ids are stable; the manifest uses them."""

    id: str
    label: str                      # plain words for the manifest and the reply
    capability: str                 # the bridge capability this source calls
    # The parameters the tool may pass. A key outside this set is refused before
    # any call — the set is CLOSED, so the model can never add a host/URL/secret.
    query_params: tuple[str, ...]
    accepts_symbols: bool           # whether `symbols` drives the pagination
    per_call_param: str             # the param that pages one call at a time
    rate_per_minute: int
    max_rows_per_call: int
    columns: tuple[str, ...]        # the exact CSV schema every row carries
    licence: str
    attribution: str


# The library. One row per source; a source without a row is unusable.
SOURCES: dict[str, AcquisitionSource] = {
    "prices_daily": AcquisitionSource(
        id="prices_daily",
        label="Daily price history",
        capability="price_history",
        query_params=("range", "interval", "market"),
        accepts_symbols=True,
        per_call_param="symbol",
        rate_per_minute=60,
        max_rows_per_call=5_000,
        columns=("symbol", "date", "open", "high", "low", "close", "volume"),
        licence="vendor terms — see attribution",
        attribution="Yahoo Finance (unofficial endpoint)",
    ),
    "macro_series": AcquisitionSource(
        id="macro_series",
        label="Economic series",
        capability="macro_series",
        query_params=("series", "quantity", "source"),
        accepts_symbols=False,
        per_call_param="series",
        rate_per_minute=30,
        max_rows_per_call=10_000,
        columns=("series", "date", "value"),
        licence="public data — see attribution",
        attribution="The series' own publisher (as reported by the provider)",
    ),
    "statements_annual": AcquisitionSource(
        id="statements_annual",
        label="Company statements",
        capability="sec_filings",
        query_params=("market",),
        accepts_symbols=True,
        per_call_param="symbol",
        rate_per_minute=10,
        max_rows_per_call=2_000,
        columns=("symbol", "period", "field", "value"),
        licence="public domain (SEC EDGAR)",
        attribution="U.S. Securities and Exchange Commission",
    ),
    "filings_list": AcquisitionSource(
        id="filings_list",
        label="Company filings index",
        capability="sec_filing_list",
        # `form` is free text validated by the bridge (SEC form vocabulary is
        # large and versioned); the dates bound the filing window.
        query_params=("form", "date_from", "date_to"),
        accepts_symbols=True,
        per_call_param="symbol",
        rate_per_minute=10,
        max_rows_per_call=2_000,
        columns=("symbol", "form", "filed", "period", "accession", "document", "description"),
        licence="public domain (SEC EDGAR)",
        attribution="U.S. Securities and Exchange Commission",
    ),
    "operator_datasets": AcquisitionSource(
        id="operator_datasets",
        label="Connected data sources",
        capability="custom_dataset_records",
        # The dataset is SELECTED by name; only datasets the operator declared
        # are reachable. `values` fills the connector's OWN declared parameters
        # (never a URL/host/secret — those are the operator's configuration).
        query_params=("dataset", "values"),
        accepts_symbols=False,
        per_call_param="dataset",
        rate_per_minute=30,
        max_rows_per_call=5_000,
        columns=("dataset", "record", "field", "value"),
        licence="as arranged by the operator with the data source",
        attribution="the operator's declared data source (Settings → Data Sources)",
    ),
}

# The values the agent may pass for each of these; anything else is refused.
CLOSED_VALUE_SETS: dict[str, tuple[str, ...]] = {
    "range": ("1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"),
    "interval": ("1d", "1wk", "1mo"),
}

# A hard ceiling on how many instruments ONE call may page through. The user can
# ask for more with a second call; the budget bounds each one.
MAX_SYMBOLS_PER_CALL = 50


def get_source(source_id: str) -> Optional[AcquisitionSource]:
    return SOURCES.get(str(source_id or "").strip())


def list_sources() -> list[dict[str, Any]]:
    return [source_public(s) for s in SOURCES.values()]


def source_public(source: AcquisitionSource) -> dict[str, Any]:
    return {
        "id": source.id,
        "label": source.label,
        "acceptsSymbols": source.accepts_symbols,
        "params": list(source.query_params),
        "licence": source.licence,
        "attribution": source.attribution,
    }


def registry_issues() -> list[str]:
    """Consistency problems, empty when every row is complete."""
    issues: list[str] = []
    for source in SOURCES.values():
        for field in ("label", "capability", "licence", "attribution", "per_call_param"):
            if not str(getattr(source, field) or "").strip():
                issues.append(f"{source.id}: missing {field}")
        if not source.query_params:
            issues.append(f"{source.id}: the parameter set must be closed, not empty")
        if source.accepts_symbols and "symbol" in source.query_params:
            issues.append(f"{source.id}: 'symbol' must not be a caller parameter")
        if not source.columns:
            issues.append(f"{source.id}: no CSV columns declared")
        if source.rate_per_minute <= 0 or source.max_rows_per_call <= 0:
            issues.append(f"{source.id}: rate and row ceiling must be positive")
        for key, allowed in CLOSED_VALUE_SETS.items():
            if key in source.query_params and not allowed:
                issues.append(f"{source.id}: parameter {key!r} has no closed value set")
    return issues


__all__ = [
    "CLOSED_VALUE_SETS",
    "MAX_SYMBOLS_PER_CALL",
    "SOURCES",
    "AcquisitionSource",
    "get_source",
    "list_sources",
    "registry_issues",
    "source_public",
]
