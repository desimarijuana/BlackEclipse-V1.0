#!/usr/bin/env python3
"""
EclipseScraper Python bridge — uses Scrapling's StealthyFetcher to fetch
a quote page and extract the price, bypassing bot detection.

Usage (from Node):
    python scripts/scrapling_service.py <symbol> <market>

Prints a JSON object to stdout:
    {"symbol": "...", "price": 123.45, "changePct": 1.23}

Exit codes:
    0  success (quote found)
    1  blocked / bot-wall
    2  structure changed (page loaded but no price found)
    3  network / timeout error
    4  invalid args
"""

import sys
import json

# Exchange codes per market for Google Finance URLs.
# Fixes the bug where all US symbols were mapped to NYSE (AAPL is NASDAQ).
US_EXCHANGE = {
    "AAPL": "NASDAQ", "MSFT": "NASDAQ", "NVDA": "NASDAQ", "GOOGL": "NASDAQ",
    "GOOG": "NASDAQ", "TSLA": "NASDAQ", "AMZN": "NASDAQ", "META": "NASDAQ",
    "AVGO": "NASDAQ", "COST": "NASDAQ", "PEP": "NASDAQ", "CSCO": "NASDAQ",
    "AMD": "NASDAQ", "ADBE": "NASDAQ", "NFLX": "NASDAQ", "TXN": "NASDAQ",
    "QCOM": "NASDAQ", "INTC": "NASDAQ", "CMCSA": "NASDAQ", "NKE": "NASDAQ",
    "ORCL": "NASDAQ", "ACN": "NYSE", "T": "NYSE", "VZ": "NYSE",
    "JPM": "NYSE", "V": "NYSE", "JNJ": "NYSE", "WMT": "NYSE", "XOM": "NYSE",
    "HD": "NYSE", "PG": "NYSE", "KO": "NYSE", "MCD": "NYSE", "DIS": "NYSE",
    "BA": "NYSE", "CAT": "NYSE", "CVX": "NYSE", "GS": "NYSE", "IBM": "NYSE",
    "MA": "NYSE", "UNH": "NYSE", "MRK": "NYSE", "ABBV": "NYSE", "BAC": "NYSE",
    "PFE": "NYSE", "TMO": "NYSE", "DHR": "NYSE", "ABT": "NYSE", "WFC": "NYSE",
    "BRK.B": "NYSE", "LLY": "NYSE", "GE": "NYSE",
}


def build_url(symbol: str, market: str) -> str:
    sym = symbol.upper()
    if market.upper() == "CRYPTO":
        return f"https://www.google.com/finance/quote/{sym}-USD"
    exchange = US_EXCHANGE.get(sym, "NASDAQ")
    return f"https://www.google.com/finance/quote/{sym}:{exchange}"


def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "usage: scrapling_service.py <symbol> <market>"}))
        sys.exit(4)

    symbol = sys.argv[1]
    market = sys.argv[2]
    url = build_url(symbol, market)

    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        print(json.dumps({"error": "scrapling not installed"}))
        sys.exit(3)

    try:
        page = StealthyFetcher.fetch(url=url)
    except Exception as e:
        print(json.dumps({"error": str(e), "symbol": symbol, "market": market}))
        sys.exit(3)

    if not page or not page.body:
        print(json.dumps({"error": "empty page", "symbol": symbol, "market": market}))
        sys.exit(3)

    # Detect a block page (captcha / bot wall) by common markers.
    body = page.get_all_text() if hasattr(page, "get_all_text") else str(page.body)
    if not body or "captcha" in body.lower() or "unusual traffic" in body.lower():
        print(json.dumps({"error": "blocked", "symbol": symbol, "market": market}))
        sys.exit(1)

    # Extract price via data-last-price attribute, else .YMlKec class, else regex.
    import re
    price = None
    change_pct = 0.0

    # 1. data-last-price attribute
    try:
        els = page.css("div[data-last-price]")
        if els:
            el = els.first
            if el:
                raw = el.attrib.get("data-last-price") if hasattr(el, "attrib") else None
                if raw:
                    price = float(raw)
    except Exception:
        price = None

    # 2. .YMlKec class (Google Finance current price)
    if price is None:
        try:
            els = page.css(".YMlKec")
            if els:
                el = els.first
                txt = el.text or ""
                txt = txt.replace("$", "").replace(",", "").strip()
                price = float(txt) if txt else None
        except Exception:
            price = None

    # 3. Generic $ amount in body text
    if price is None:
        try:
            m = re.search(r"\$\s?([\d,]+\.?\d*)", body)
            if m:
                price = float(m.group(1).replace(",", ""))
        except Exception:
            price = None

    # Extract change percent from body text (e.g. "+1.34%", "-0.50%")
    try:
        # Prefer the first +/- percent that appears near the price block.
        m = re.search(r"([+-]\d+\.\d+)%", body)
        if m:
            change_pct = float(m.group(1))
    except Exception:
        change_pct = 0.0

    if price is None or price <= 0:
        print(json.dumps({"error": "structure_changed", "symbol": symbol, "market": market}))
        sys.exit(2)

    print(json.dumps({"symbol": symbol, "market": market, "price": price, "changePct": change_pct}))
    sys.exit(0)


if __name__ == "__main__":
    main()
