"""Data Quality Engine — validate every market record before it is presented.

The directive makes this mandatory. Every response is evaluated for:

  * freshness (is this value old enough to be misleading?),
  * timestamp validity (is the as-of real or unknown?),
  * schema correctness (required fields present),
  * duplicates (repeated timestamps),
  * gaps (missing bars in a series),
  * outliers (impossible jumps),
  * negative/invalid values (a negative price/volume),
  * OHLC consistency (high >= low, low <= open/close <= high),
  * provider conflicts (the same fact from two sources, materially different).

Findings are advisory: a `warning` is surfaced and the value is kept; an
`invalid` finding withholds the value (the gateway never emits it as clean). The
engine NEVER silently repairs a value — it reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .config import get_config
from .models import (
    HistoricalPriceSeries,
    OrderBook,
    QualityStatus,
    Quote,
)


@dataclass
class QualityFinding:
    kind: str            # freshness | timestamp | schema | duplicate | gap | outlier | invalid_value | ohlc | conflict
    severity: str        # warning | invalid
    detail: str
    field: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        out = {"kind": self.kind, "severity": self.severity, "detail": self.detail}
        if self.field:
            out["field"] = self.field
        return out


@dataclass
class QualityReport:
    status: QualityStatus = "unknown"
    findings: list[QualityFinding] = field(default_factory=list)

    @property
    def invalid(self) -> bool:
        return any(f.severity == "invalid" for f in self.findings)

    def add(self, kind: str, severity: str, detail: str, field: Optional[str] = None) -> None:
        self.findings.append(QualityFinding(kind, severity, detail, field))

    def finalize(self) -> "QualityReport":
        if self.invalid:
            self.status = "invalid"
        elif any(f.severity == "warning" for f in self.findings):
            self.status = "warning"
        else:
            # `info` findings (e.g. a closed-market note) are surfaced but never
            # downgrade a value's status.
            self.status = "valid"
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "findings": [f.to_dict() for f in self.findings]}


def _age_seconds(ts: Optional[str]) -> Optional[float]:
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
    now = _dt.datetime.now(_dt.timezone.utc)
    return (now - parsed).total_seconds()


def check_negative(report: QualityReport, name: str, value: Any) -> None:
    """A price/volume/quantity can never be negative."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value < 0:
        report.add("invalid_value", "invalid", f"{name} is negative ({value})", field=name)


def check_ohlc(report: QualityReport, bar: Any) -> None:
    """OHLC consistency: high >= low and low <= open/close <= high."""
    o, h, low, c = bar.open, bar.high, bar.low, bar.close
    for name, value in (("open", o), ("high", h), ("low", low), ("close", c)):
        check_negative(report, f"ohlc.{name}", value)
    if isinstance(h, (int, float)) and isinstance(low, (int, float)) and h < low:
        report.add("ohlc", "invalid",
                   f"bar {bar.timestamp}: high ({h}) < low ({low})", field="high")
    for name, value in (("open", o), ("close", c)):
        if (
            isinstance(value, (int, float))
            and isinstance(h, (int, float))
            and isinstance(low, (int, float))
            and (value > h or value < low)
        ):
            report.add("ohlc", "warning",
                       f"bar {bar.timestamp}: {name} ({value}) outside [low={low}, high={h}]",
                       field=name)


def check_series(report: QualityReport, series: HistoricalPriceSeries) -> None:
    """Duplicate timestamps, gaps and outliers for a bar series."""
    seen: set[str] = set()
    dupes = 0
    ordered = sorted(series.bars, key=lambda b: b.timestamp)
    prev_close: Optional[float] = None
    outliers = 0
    for bar in ordered:
        check_ohlc(report, bar)
        if bar.timestamp in seen:
            dupes += 1
        seen.add(bar.timestamp)
        if (
            isinstance(bar.close, (int, float))
            and prev_close not in (None, 0)
            and isinstance(prev_close, (int, float))
        ):
            move = abs(bar.close - prev_close) / abs(prev_close)
            # A >50% single-bar move is almost always a data error or a split the
            # provider did not adjust for. Flagged, never repaired.
            if move > 0.5:
                outliers += 1
                if outliers <= 3:
                    report.add("outlier", "warning",
                               f"bar {bar.timestamp}: {move:.0%} move vs prior close",
                               field="close")
        if isinstance(bar.close, (int, float)):
            prev_close = bar.close
    series.duplicate_timestamps = dupes
    if dupes:
        report.add("duplicate", "warning",
                   f"{dupes} duplicate timestamp(s) in series")
    if series.gaps:
        report.add("gap", "warning",
                   f"{len(series.gaps)} gap(s) detected across the requested range")


def check_freshness(report: QualityReport, timestamp: Optional[str], freshness: str,
                    *, asset_type: Optional[str] = None, market: Optional[str] = None) -> Optional[float]:
    """Flag a value older than the freshness window allows. Returns age seconds.

    A closed market is NOT staleness: when the session is closed and the value is
    at/after the last close, the finding is downgraded to an informational note
    (`session`) rather than a warning, so a correctly frozen market is never
    mislabelled.
    """
    age = _age_seconds(timestamp)
    if age is None:
        report.add("timestamp", "warning", "no usable as-of timestamp", field="timestamp")
        return None
    cfg = get_config()
    if freshness == "realtime" and age > cfg.realtime_max_age_s:
        try:
            from .calendar import assess  # local import: no cycle

            session = assess(asset_type, timestamp, market=market)
        except Exception:  # noqa: BLE001 - calendar is best-effort
            session = {"state": "unknown", "reason": ""}
        if session.get("state") == "closed_recent":
            report.add("session", "info", session.get("reason") or "market closed",
                       field="timestamp")
        else:
            report.add("freshness", "warning",
                       f"value is {age:.0f}s old (realtime allows {cfg.realtime_max_age_s:.0f}s)",
                       field="timestamp")
    return age


def check_orderbook(report: QualityReport, book: OrderBook) -> None:
    """Crossed/locked books, negative levels, depth sanity."""
    if isinstance(book.best_bid, (int, float)) and isinstance(book.best_ask, (int, float)):
        if book.best_bid > book.best_ask:
            report.add("invalid_value", "invalid",
                       f"crossed book: best bid {book.best_bid} > best ask {book.best_ask}")
        elif book.best_bid == book.best_ask:
            report.add("invalid_value", "warning",
                       f"locked book: best bid == best ask ({book.best_bid})")
    for level in [*book.bids, *book.asks]:
        check_negative(report, "level.price", level.price)
        check_negative(report, "level.quantity", level.quantity)


def evaluate_quote(quote: Quote) -> QualityReport:
    report = QualityReport()
    if quote.price is None:
        report.add("schema", "invalid", "quote has no price", field="price")
    check_negative(report, "price", quote.price)
    check_negative(report, "volume", quote.volume)
    check_negative(report, "bid", quote.bid)
    check_negative(report, "ask", quote.ask)
    if quote.bid is not None and quote.ask is not None and quote.bid > quote.ask:
        report.add("invalid_value", "invalid",
                   f"crossed quote: bid {quote.bid} > ask {quote.ask}")
    age = check_freshness(
        report, quote.timestamp or quote.meta.event_time, quote.meta.freshness,
        asset_type=quote.meta.asset_type, market=quote.meta.exchange,
    )
    quote.age_seconds = age
    return report.finalize()


def evaluate_series(series: HistoricalPriceSeries) -> QualityReport:
    report = QualityReport()
    if not series.bars:
        report.add("schema", "invalid", "series has no bars", field="bars")
    else:
        check_series(report, series)
    return report.finalize()


def evaluate_orderbook(book: OrderBook) -> QualityReport:
    report = QualityReport()
    if not book.bids and not book.asks:
        report.add("schema", "invalid", "order book is empty", field="bids")
    check_orderbook(report, book)
    return report.finalize()


def evaluate(record: Any, capability: str) -> QualityReport:
    """Dispatch to the right evaluator by capability, then apply generic checks."""
    if capability == "quote":
        report = evaluate_quote(record)
    elif capability in ("historical", "ohlcv"):
        report = evaluate_series(record)
    elif capability == "orderbook":
        report = evaluate_orderbook(record)
    else:
        report = QualityReport()
        # Generic negative-value sweep for scalar records with common fields.
        for name in ("price", "volume", "market_cap", "open_interest", "rate", "mid"):
            check_negative(report, name, getattr(record, name, None))
        report.finalize()
    # Propagate findings to the record's meta so consumers can see them.
    if report.findings:
        record.meta.warnings = [*record.meta.warnings, *[f.detail for f in report.findings]]
    record.meta.quality = report.status
    if report.invalid:
        record.meta.data_status = "UNAVAILABLE"
    return report


__all__ = [
    "QualityFinding",
    "QualityReport",
    "evaluate",
    "evaluate_orderbook",
    "evaluate_quote",
    "evaluate_series",
]
