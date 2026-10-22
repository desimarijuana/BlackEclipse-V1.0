"""The durable half of the market cache: history that survives a restart.

The gateway caches history **in process**, so every restart re-fetches every
bar from the provider. This module adds the durable half on top of the
existing `SeriesStore`: the bars the runtime has already paid for are kept,
and a later request for the same window is served from them.

That is the engineering half of "bundled data". It does not buy a vendor's
history - it buys **one copy of the history Eclipse has already seen**, on the
machine, offline, reproducible. The same bars then feed the backtest, the
regime classifier, the Monte-Carlo, the Pine engine and the trade-log
analysis, so all five agree by construction.

The rules:

- **A cached window is served only when it actually covers the request.** A
  partial cache is a miss, not a short answer.
- **A miss fetches and MERGES.** The store's key is
  (symbol, interval, provider, adjusted, eventTime), so a later fetch replaces
  the bars it overlaps and adds the ones it missed.
- **A stale tail is refetched.** With no explicit window, a cache whose last
  bar is older than the freshness horizon is a miss: history grows, and a
  cache that never refreshes would silently freeze the market.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

#: How stale a cached tail may be before it is refetched (in days). Daily bars
#: land once a day; anything older is refetched.
DEFAULT_MAX_AGE_DAYS = 1


def _parse(stamp: Any) -> Optional[datetime]:
    if stamp is None:
        return None
    text = str(stamp).strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


class HistoryCache:
    """Durable bar history, served from the ONE series store."""

    def __init__(self, series_store: Any, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> None:
        self._store = series_store
        self.max_age_days = max(0, int(max_age_days))

    @property
    def available(self) -> bool:
        return self._store is not None

    def coverage(self, symbol: str, interval: str = "1d", *, adjusted: bool = True
                 ) -> dict[str, Any]:
        if not self.available:
            return {"symbol": symbol, "interval": interval, "barCount": 0,
                    "start": None, "end": None}
        return self._store.coverage(symbol, interval, adjusted=adjusted)

    def lookup(self, symbol: str, interval: str = "1d", *, adjusted: bool = True,
               start: Optional[str] = None, end: Optional[str] = None,
               now: Optional[datetime] = None) -> Optional[list[dict[str, Any]]]:
        """The cached bars for a window, or None when the cache does not cover it.

        `None` means MISS - the caller must fetch. An empty list is never
        returned, so a miss can never be mistaken for "there is no history".
        """
        if not self.available:
            return None
        try:
            rows = self._store.get_bars(symbol, interval, adjusted=adjusted,
                                        start=start, end=end)
        except Exception:  # noqa: BLE001 - a cache read failure is a miss
            return None
        if not rows:
            return None

        first = _parse(rows[0].get("timestamp"))
        last = _parse(rows[-1].get("timestamp"))
        if first is None or last is None:
            return None

        if start:
            wanted = _parse(start)
            if wanted is not None and first > wanted:
                return None          # the cache does not reach back far enough
        if end:
            wanted = _parse(end)
            if wanted is not None and last < wanted:
                return None          # the cache does not reach forward far enough
        if not start and not end:
            # No window: the cache is only the whole history if its tail is
            # still fresh. Otherwise the market has moved on and must be fetched.
            moment = now or datetime.now(timezone.utc)
            if (moment - last) > timedelta(days=self.max_age_days + 1):
                return None
        return rows

    def store(self, symbol: str, interval: str, provider: str, adjusted: bool,
              rows: list[dict[str, Any]]) -> int:
        """Keep the bars we just fetched, so the next request is a hit."""
        if not self.available or not rows:
            return 0
        try:
            return int(self._store.save_bars(symbol, interval, provider, adjusted, rows))
        except Exception:  # noqa: BLE001 - persistence is best-effort
            return 0


__all__ = ["DEFAULT_MAX_AGE_DAYS", "HistoryCache"]
