#!/usr/bin/env python3
"""Bulk country universe importer for Black Eclipse.

Pulls official index constituent lists from Wikipedia, normalizes tickers
for the yfinance bridge, verifies each symbol against Yahoo's chart endpoint,
and imports verified symbols into JDDS. Skips symbols already present.

Usage:  python scripts/import-bulk-universe.py [market1,market2,...]
"""
import io
import re
import sqlite3
import sys
import urllib.request
from pathlib import Path

import pandas as pd

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
DB_PATH = Path(__file__).resolve().parent.parent / "jdds.db"

# market -> (wikipedia URL, table index with header=None, symbol col, name col)
SOURCES = {
    "FR": ("https://en.wikipedia.org/wiki/CAC_40", 4, 3, 0),
    "DE": ("https://en.wikipedia.org/wiki/DAX", 4, 0, 2),
    "JP": ("https://de.wikipedia.org/wiki/Nikkei_225", 8, 1, 2),
    "KR": ("https://en.wikipedia.org/wiki/KOSPI_200", 2, 1, 0),
    "HK": ("https://en.wikipedia.org/wiki/Hang_Seng_Index", 6, 0, 1),
    "CN": ("https://en.wikipedia.org/wiki/SZSE_100_Index", 1, 0, 1),
    "IN": ("https://en.wikipedia.org/wiki/NIFTY_50", 1, 1, 0),
    "SG": ("https://en.wikipedia.org/wiki/Straits_Times_Index", 3, 0, 1),
    "MY": ("https://en.wikipedia.org/wiki/FTSE_Bursa_Malaysia_KLCI", 2, 1, 0),
    "TH": ("https://en.wikipedia.org/wiki/SET50_Index", 0, 0, 1),
    "CA": ("https://en.wikipedia.org/wiki/S%26P/TSX_60", 1, 0, 1),
    "AU": ("https://en.wikipedia.org/wiki/S%26P/ASX_200", 2, 0, 1),
    "UK": ("https://en.wikipedia.org/wiki/FTSE_100_Index", 6, 1, 0),
    "NL": ("https://en.wikipedia.org/wiki/AEX_index", 3, 0, 1),
    "ID": ("https://en.wikipedia.org/wiki/LQ45", 1, 0, 1),
    "BR": ("https://en.wikipedia.org/wiki/List_of_companies_listed_on_B3", 0, 1, 0),
}

# markets whose Wikipedia table already ships the full Yahoo-style suffix
FULL_SUFFIX_SOURCES = {"FR", "DE", "UK", "NL"}

MARKET_SUFFIX = {
    "FR": ".PA", "DE": ".DE", "JP": ".T", "KR": ".KS", "HK": ".HK", "CN": ".SS",
    "TW": ".TW", "IN": ".NS", "SG": ".SI", "AU": ".AX", "CA": ".TO", "BR": ".SA",
    "SA": ".SR", "ZA": ".JO", "EG": ".CA", "RU": ".ME", "TH": ".BK", "VN": ".VN",
    "MY": ".KL", "NL": ".AS", "UK": ".L",
}

EXCHANGE_INFO = {
    "FR": ("Euronext Paris", "Europe/Paris"), "DE": ("XETRA", "Europe/Berlin"),
    "JP": ("TSE", "Asia/Tokyo"), "KR": ("KRX", "Asia/Seoul"), "HK": ("HKEX", "Asia/Hong_Kong"),
    "CN": ("SSE/SZSE", "Asia/Shanghai"), "IN": ("NSE", "Asia/Kolkata"), "SG": ("SGX", "Asia/Singapore"),
    "MY": ("Bursa Malaysia", "Asia/Kuala_Lumpur"), "TH": ("SET", "Asia/Bangkok"), "CA": ("TSX", "America/Toronto"),
    "AU": ("ASX", "Australia/Sydney"), "UK": ("LSE", "Europe/London"), "NL": ("Euronext Amsterdam", "Europe/Amsterdam"),
    "ID": ("IDX", "Asia/Jakarta"), "BR": ("B3", "America/Sao_Paulo"),
}

OPEN_HOUR = {"FR": 9, "DE": 9, "JP": 9, "KR": 9, "HK": 9, "CN": 9, "IN": 9, "SG": 9,
             "MY": 9, "TH": 10, "CA": 9, "AU": 10, "UK": 8, "NL": 9, "ID": 9, "BR": 10}
CLOSE_HOUR = {"FR": 17, "DE": 17, "JP": 15, "KR": 15, "HK": 16, "CN": 15, "IN": 15, "SG": 17,
              "MY": 17, "TH": 16, "CA": 16, "AU": 16, "UK": 16, "NL": 17, "ID": 15, "BR": 17}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "ignore")


def normalize_symbol(raw, market):
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return None
    # Pandas may read numeric codes as floats: 9983.0 -> 9983
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    # Strip exchange prefixes: "SEHK: 5", "SGX: A17U", "SZSE: 300750", "IDX: AADI"
    s = re.sub(r"^[A-Z]+:\s*", "", s)
    s = s.replace("\xa0", " ").strip()
    if market in FULL_SUFFIX_SOURCES:
        return s  # AC.PA / ADS.DE / III / ABN.AS already have suffix
    suffix = MARKET_SUFFIX.get(market, "")
    if suffix and s.endswith(suffix):
        s = s[: -len(suffix)]
    # HK numeric codes must be zero-padded to 4 digits: 5 -> 0005, 388 -> 0388
    if market == "HK" and re.fullmatch(r"\d{1,4}", s):
        s = s.zfill(4)
    return s


def yahoo_resolve(symbol, market):
    if market == "CN" and re.fullmatch(r"\d{6}", symbol):
        return symbol + (".SZ" if symbol[0] in "03" else ".SS")
    suffix = MARKET_SUFFIX.get(market, "")
    if not suffix:
        return symbol
    return symbol if symbol.endswith(suffix) else symbol + suffix


def verify_on_yahoo(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(600).decode("utf-8", "ignore")
        return resp.status == 200 and '"meta"' in body and '"error"' not in body
    except Exception:
        return False


def extract(market):
    url, table_idx, sym_col, name_col = SOURCES[market]
    html = fetch(url)
    tables = pd.read_html(io.StringIO(html), header=None)
    t = tables[table_idx]
    rows = []
    for _, row in t.iterrows():
        try:
            vals = row.tolist()
            sym = normalize_symbol(vals[sym_col], market)
            name = str(vals[name_col]).strip()
        except Exception:
            continue
        if not sym or name.lower() == "nan":
            continue
        rows.append((sym, name))
    seen = set()
    uniq = []
    for sym, name in rows:
        if sym in seen:
            continue
        seen.add(sym)
        uniq.append((sym, name))
    return uniq


def ensure_market(con, market):
    exchange, tz = EXCHANGE_INFO.get(market, (market, "UTC"))
    con.execute(
        """INSERT OR IGNORE INTO Market (id, country, exchange, timezone, openHour, closeHour, enabled, isCrypto, createdAt)
           VALUES (?,?,?,?,?,?,1,0,datetime('now'))""",
        (market, market, exchange, tz, OPEN_HOUR.get(market, 9), CLOSE_HOUR.get(market, 16)),
    )


def main():
    filter_markets = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    for market in SOURCES:
        if filter_markets and market not in filter_markets:
            continue
        try:
            rows = extract(market)
        except Exception as e:
            print(f"{market}: EXTRACT FAIL {e}")
            continue
        ensure_market(con, market)
        added = skipped = dead = 0
        for bare, name in rows:
            exists = cur.execute("SELECT id FROM Asset WHERE marketId=? AND symbol=?", (market, bare)).fetchone()
            if exists:
                skipped += 1
                continue
            ticker = yahoo_resolve(bare, market)
            if verify_on_yahoo(ticker):
                cur.execute(
                    "INSERT INTO Asset (id, symbol, name, marketId, isActive) VALUES (lower(hex(randomblob(8))),?,?,?,1)",
                    (bare, name, market),
                )
                added += 1
            else:
                dead += 1
        con.commit()
        print(f"{market}: +{added} added, {skipped} existing, {dead} dead/unverified")
    con.close()
    print("Done.")


if __name__ == "__main__":
    main()
