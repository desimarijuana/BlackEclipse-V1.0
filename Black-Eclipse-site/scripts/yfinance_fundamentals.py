#!/usr/bin/env python3
"""Fundamentals bridge for Black Eclipse.

Fetches annual financial statements + profile/ratios for ONE Yahoo ticker and
emits a normalized JSON document on stdout. This is the Yahoo provider in the
fundamentals layer (a secondary/fallback source behind SEC EDGAR for US issuers).

    python scripts/yfinance_fundamentals.py <YAHOO_TICKER>

Stdout is pure JSON. The caller resolves the market suffix via the shared
`yahooSymbol()` helper, so this script never guesses exchange suffixes.

Only the statement rows the Eclipse schema needs are read (plus a small,
fixed subset of `info`) — the full yfinance statement frames are huge and the
whole payload crosses an IPC pipe.
"""

import contextlib
import io
import json
import math
import sys

import yfinance as yf


def num(v):
    """Coerce a pandas/numpy scalar to a JSON-safe float or None."""
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def value(df, row, col):
    """Read one statement cell, tolerating missing rows/columns."""
    try:
        if row not in df.index:
            return None
        return num(df.at[row, col])
    except Exception:
        return None


# yfinance statement row labels → Eclipse period field. First present wins.
INCOME_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "costOfRevenue": ["Cost Of Revenue", "Reconciled Cost Of Revenue"],
    "grossProfit": ["Gross Profit"],
    "operatingIncome": ["Operating Income", "Total Operating Income As Reported", "EBIT"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "netIncome": ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "taxProvision": ["Tax Provision"],
    "pretaxIncome": ["Pretax Income"],
    "researchDevelopment": ["Research And Development"],
    "interestExpense": ["Interest Expense", "Interest Expense Non Operating"],
}
CASHFLOW_MAP = {
    "operatingCashFlow": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure", "Purchase Of PPE"],
    "freeCashFlow": ["Free Cash Flow"],
    "dividendsPaid": ["Common Stock Dividend Paid", "Cash Dividends Paid"],
    "depreciation": ["Depreciation And Amortization", "Depreciation Amortization Depletion"],
}
BALANCE_MAP = {
    "totalAssets": ["Total Assets"],
    "totalLiabilities": ["Total Liabilities Net Minority Interest"],
    "totalEquity": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "totalDebt": ["Total Debt"],
    "netDebt": ["Net Debt"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash Financial"],
    "currentAssets": ["Current Assets"],
    "currentLiabilities": ["Current Liabilities"],
    "inventory": ["Inventory"],
    "currentDebt": ["Current Debt", "Current Debt And Capital Lease Obligation"],
    "longTermDebt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "accountsReceivable": ["Accounts Receivable", "Receivables"],
    "sharesOutstanding": ["Ordinary Shares Number", "Share Issued"],
}

INFO_KEYS = [
    "longName", "shortName", "sector", "industry", "country", "currency",
    "financialCurrency", "website", "longBusinessSummary", "fullTimeEmployees",
    "marketCap", "enterpriseValue", "currentPrice", "previousClose", "beta",
    "trailingPE", "forwardPE", "pegRatio", "trailingPegRatio", "priceToBook",
    "priceToSalesTrailing12Months", "enterpriseToEbitda", "enterpriseToRevenue",
    "trailingEps", "forwardEps", "epsTrailingTwelveMonths", "epsForward",
    "dividendRate", "dividendYield", "trailingAnnualDividendRate",
    "trailingAnnualDividendYield", "payoutRatio", "fiveYearAvgDividendYield",
    "totalCash", "totalDebt", "returnOnEquity", "returnOnAssets",
    "grossMargins", "operatingMargins", "profitMargins", "ebitdaMargins",
    "revenueGrowth", "earningsGrowth", "earningsQuarterlyGrowth",
    "currentRatio", "quickRatio", "debtToEquity", "bookValue",
    "revenuePerShare", "freeCashflow", "operatingCashflow", "totalRevenue",
    "grossProfits", "ebitda", "netIncomeToCommon",
    "heldPercentInstitutions", "heldPercentInsiders", "sharesOutstanding",
    "floatShares", "sharesShort", "shortPercentOfFloat", "shortRatio",
    "recommendationKey", "recommendationMean", "numberOfAnalystOpinions",
    "targetHighPrice", "targetLowPrice", "targetMeanPrice", "targetMedianPrice",
    "averageAnalystRating", "mostRecentQuarter", "lastFiscalYearEnd",
    "nextFiscalYearEnd", "earningsTimestamp", "earningsTimestampStart",
    "earningsTimestampEnd", "isEarningsDateEstimate", "exchange",
    "fullExchangeName", "quoteType", "allTimeHigh", "allTimeLow",
]


def build_periods(ticker):
    with contextlib.redirect_stdout(io.StringIO()):
        income = ticker.income_stmt
        cashflow = ticker.cashflow
        balance = ticker.balance_sheet
    if income is None or income.empty:
        return []
    cols = list(income.columns)
    periods = []
    for col in cols:
        try:
            end_date = str(col.date())
        except Exception:
            continue
        p = {"endDate": end_date}
        for field, rows in INCOME_MAP.items():
            p[field] = next((value(income, r, col) for r in rows if value(income, r, col) is not None), None)
        for field, rows in CASHFLOW_MAP.items():
            if cashflow is not None and not cashflow.empty and col in cashflow.columns:
                p[field] = next((value(cashflow, r, col) for r in rows if value(cashflow, r, col) is not None), None)
            else:
                p[field] = None
        for field, rows in BALANCE_MAP.items():
            if balance is not None and not balance.empty and col in balance.columns:
                p[field] = next((value(balance, r, col) for r in rows if value(balance, r, col) is not None), None)
            else:
                p[field] = None
        periods.append(p)
    # Oldest first — the schema and charts read left-to-right in time.
    periods.sort(key=lambda x: x["endDate"])
    return periods


def build_earnings(ticker):
    """Reported vs estimated EPS per quarter, when yfinance exposes it."""
    out = {"history": [], "estimates": []}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            ed = ticker.get_earnings_dates(limit=12)
    except Exception:
        return out
    if ed is None or ed.empty:
        return out
    for idx, row in ed.iterrows():
        try:
            date = str(idx.date())
        except Exception:
            continue
        actual = None
        estimate = None
        for key in ("Reported EPS", "ReportedEPS"):
            if key in row:
                actual = num(row[key])
        for key in ("EPS Estimate", "EPSEstimate"):
            if key in row:
                estimate = num(row[key])
        if actual is None and estimate is None:
            continue
        out["history"].append({"date": date, "actual": actual, "estimate": estimate})
    out["history"].sort(key=lambda x: x["date"])
    return out


def run():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        return {"error": "usage: yfinance_fundamentals.py <YAHOO_TICKER>"}
    symbol = sys.argv[1].strip().upper()
    with contextlib.redirect_stdout(io.StringIO()):
        ticker = yf.Ticker(symbol)
        periods = build_periods(ticker)
        try:
            raw_info = ticker.info or {}
        except Exception:
            raw_info = {}
        earnings = build_earnings(ticker)
    if not periods and not raw_info:
        return {"error": f"no fundamentals for {symbol} (delisted, non-equity, or rate limited)"}
    info = {k: raw_info.get(k) for k in INFO_KEYS if raw_info.get(k) is not None}
    return {
        "symbol": symbol,
        "currency": raw_info.get("financialCurrency") or raw_info.get("currency"),
        "info": info,
        "periods": periods,
        "earnings": earnings,
    }


def main():
    with contextlib.redirect_stdout(io.StringIO()):
        result = run()
    print(json.dumps(result, default=str))
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
