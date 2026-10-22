#!/usr/bin/env python3
"""Batch yfinance bridge for Black Eclipse.

Spawns once per batch instead of one HTTP round-trip per symbol:
    python scripts/yfinance_bridge.py <market> <sym1,sym2,...> [interval] [period]

Fast path (default): quotes via Ticker(sym).fast_info — chart endpoint only,
never .info (Yahoo rate-limits/401s that one).
OHLC path (interval/period given): one shared yf.download() call for all symbols.

Stdout is pure JSON. Never print anything else.
"""

import contextlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import yfinance as yf

# Market id -> Yahoo ticker suffix. Keep in sync with src/lib/yfinance.ts.
MARKET_SUFFIX = {
    "US": "",
    "PK": ".PSX",
    "IN": ".NS",
    "CN": ".SS",
    "TW": ".TW",
    "JP": ".T",
    "HK": ".HK",
    "KR": ".KS",
    "SG": ".SI",
    "MY": ".KL",
    "AU": ".AX",
    "UK": ".L",
    "DE": ".DE",
    "FR": ".PA",
    "NL": ".AS",
    "CA": ".TO",
    "BR": ".SA",
    "MX": ".MX",
    "SA": ".SR",
    "AE": ".AE",
    "ZA": ".JO",
    "EG": ".CA",
    "NG": ".NG",
    "RU": ".ME",
    "TR": ".IS",
    "ID": ".JK",
    "TH": ".BK",
    "VN": ".VN",
    "CRYPTO": "-USD",
}

VALID_PERIODS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}
VALID_INTERVALS = {"1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"}


def yahoo_symbol(symbol, market):
    suffix = MARKET_SUFFIX.get(market, "")
    sym = str(symbol).strip()
    # China: 6xxxxx -> Shanghai (.SS), 0/3xxxxx -> Shenzhen (.SZ), 4/8xxxxx -> Beijing (.BJ).
    if market == "CN" and sym.isdigit() and len(sym) == 6:
        if sym.startswith(("0", "3")):
            suffix = ".SZ"
        elif sym.startswith(("4", "8")):
            suffix = ".BJ"
        else:
            suffix = ".SS"
    if not suffix:
        return sym
    if sym.endswith(suffix):
        return sym
    return f"{sym}{suffix}"


def fast_get(fast, *names):
    """First non-null value among candidate field names (camel/snake variants)."""
    for name in names:
        try:
            val = fast.get(name)
        except Exception:
            continue
        if val is not None and val == val and val != "N/A":
            return val
    return None


def fetch_quote(ticker_sym):
    """Return (symbol, quote dict | None) for one ticker via fast_info."""
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            fast = yf.Ticker(ticker_sym).fast_info
        last = fast_get(fast, "last_price", "lastPrice", "regular_market_price")
        if not last or last <= 0:
            return ticker_sym, None
        prev = fast_get(fast, "previous_close", "regularMarketPreviousClose", "regular_market_previous_close")
        prev = float(prev) if prev else None
        change_pct = ((last - prev) / prev) * 100 if prev and prev > 0 else 0.0
        vol = fast_get(fast, "last_volume", "lastVolume", "regular_market_volume")
        open_ = fast_get(fast, "open")
        high = fast_get(fast, "day_high", "dayHigh")
        low = fast_get(fast, "day_low", "dayLow")
        # Market capitalisation, when the provider exposes it. Carried so the
        # retrieval layer can VERIFY a cap against the stored snapshot instead of
        # silently falling back to a possibly stale vault value.
        mcap = fast_get(fast, "market_cap", "marketCap")
        quote = {
            "symbol": ticker_sym,
            "price": round(float(last), 6),
            "prevClose": round(float(prev), 6) if prev else None,
            "changePct": round(float(change_pct), 4),
            "open": float(open_) if open_ else None,
            "dayHigh": float(high) if high else None,
            "dayLow": float(low) if low else None,
            "volume": float(vol) if vol else None,
            "marketCap": float(mcap) if mcap else None,
        }
        return ticker_sym, quote
    except Exception:
        return ticker_sym, None


def fetch_quotes(symbols):
    """Fetch quotes with a dot->dash fallback (BRK.B -> BRK-B) per symbol."""
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(symbols)))) as pool:
        results = dict(pool.map(fetch_quote, symbols))
    missing = {s for s in symbols if results.get(s) is None}
    if missing:
        alternates = {s.replace(".", "-"): s for s in missing if "." in s}
        if alternates:
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(alternates)))) as pool:
                alt_results = dict(pool.map(fetch_quote, list(alternates.keys())))
            for alt_sym, quote in alt_results.items():
                if quote is not None:
                    results[alternates[alt_sym]] = quote
    return {sym: q for sym, q in results.items() if q is not None}


def fetch_history(symbols, period, interval, start=None, end=None):
    # An EXPLICIT window is passed to yfinance as start/end, not as a rolling
    # `period`: a 1y range is anchored to "now" and its first session can fall
    # outside the requested window (a request for 2025-10-20..2026-10-20 came
    # back starting on the 21st — a silently short series that changes every
    # return, drawdown and statistic computed from it).
    kwargs = dict(
        tickers=" ".join(symbols),
        interval=interval,
        group_by="ticker",
        progress=False,
        threads=True,
        auto_adjust=False,
    )
    if start:
        kwargs["start"] = start
        if end:
            # yfinance's `end` is EXCLUSIVE; our window's end date is inclusive.
            # Asking for the end date itself drops the last session.
            try:
                import datetime as _dt

                inclusive_end = (
                    _dt.date.fromisoformat(str(end)[:10]) + _dt.timedelta(days=1)
                ).isoformat()
            except Exception:
                inclusive_end = end
            kwargs["end"] = inclusive_end
    else:
        kwargs["period"] = period
    data = yf.download(**kwargs)
    history = {}
    for sym in symbols:
        if isinstance(data.columns, pd.MultiIndex):
            df = data[sym] if sym in data.columns.levels[0] else None
        elif len(symbols) == 1:
            df = data
        else:
            df = None
        if df is None or df.empty:
            continue
        df = df.drop(columns=["Adj Close"], errors="ignore")
        for col in ("Dividends", "Stock Splits"):
            if col in df.columns and df[col].dropna().empty:
                df = df.drop(columns=[col])
        if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = df[df["Open"] > 0]
        rows = []
        for idx, r in df.iterrows():
            row = {
                "date": str(idx.date()),
                "open": round(float(r.Open), 6) if r.Open == r.Open else None,
                "high": round(float(r.High), 6) if r.High == r.High else None,
                "low": round(float(r.Low), 6) if r.Low == r.Low else None,
                "close": round(float(r.Close), 6) if r.Close == r.Close else None,
                "volume": float(r.Volume) if r.Volume == r.Volume else None,
            }
            # Corporate actions, when yfinance reports them on this bar. Carried so
            # the fact engine can flag a split/dividend that makes a naive
            # historical comparison invalid (Universal-financial-fact §17).
            if "Dividends" in df.columns:
                div = r.get("Dividends")
                if div is not None and div == div and float(div) != 0:
                    row["dividend"] = round(float(div), 6)
            if "Stock Splits" in df.columns:
                split = r.get("Stock Splits")
                if split is not None and split == split and float(split) != 0:
                    row["split"] = round(float(split), 6)
            rows.append(row)
        if rows:
            history[sym] = rows
    return history


def main():
    # The bridge's stdout must be pure JSON — capture any library logging
    # (yfinance worker threads print delisted/404 notices) so only the final
    # payload lands on stdout.
    with contextlib.redirect_stdout(io.StringIO()):
        result = run()
    print(json.dumps(result, default=str))
    if "error" in result:
        sys.exit(1)


def run():
    if len(sys.argv) < 3:
        return {"error": "usage: yfinance_bridge.py <market> <sym1,sym2,...> [interval] [period] [start] [end]"}

    market = sys.argv[1].upper()
    raw_symbols = [s.strip().upper() for s in sys.argv[2].split(",") if s.strip()]
    interval = sys.argv[3].lower() if len(sys.argv) > 3 and sys.argv[3] else "1d"
    period = sys.argv[4].lower() if len(sys.argv) > 4 and sys.argv[4] else "1d"
    # An explicit window (start[/end]) overrides the rolling period.
    start = sys.argv[5].strip() if len(sys.argv) > 5 and sys.argv[5] else None
    end = sys.argv[6].strip() if len(sys.argv) > 6 and sys.argv[6] else None

    if not raw_symbols:
        return {"error": "no symbols given"}

    tickers = [yahoo_symbol(s, market) for s in raw_symbols]

    want_history = interval != "1d" or period not in ("", "1d") or bool(start)
    if want_history and interval in VALID_INTERVALS and (period in VALID_PERIODS or start):
        try:
            history = fetch_history(tickers, period, interval, start=start, end=end)
            return {"market": market, "history": history}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"history failed: {exc}"}

    try:
        quotes = fetch_quotes(tickers)
        if not quotes:
            return {"error": "all quotes failed (rate limited or bad symbols)"}
        return {"market": market, "quotes": quotes}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"quotes failed: {exc}"}


if __name__ == "__main__":
    main()
