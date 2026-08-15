// HTTP + cheerio fetcher — tries to extract a price from a public quote page.
// Uses rotating User-Agents and graceful failure classification.

import axios from "axios";
import * as cheerio from "cheerio";
import type { FetchResult, Quote } from "../types";
import { toErrorLike } from "../types";

const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
];

function randomUA(): string {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

// Google Finance quote page parser (clean HTML, widely used).
function parseGoogleFinance(html: string, symbol: string): Quote | null {
  const $ = cheerio.load(html);
  // Google Finance shows price in the last quote element.
  const priceEl = $("div[data-last-price]").first();
  if (priceEl.length) {
    const price = parseFloat(priceEl.attr("data-last-price") || "");
    if (!isNaN(price) && price > 0) {
      const changeEl = $("div[data-change-percent]").first();
      let changePct = 0;
      if (changeEl.length) {
        const raw = (changeEl.attr("data-change-percent") || "0").replace("%", "");
        changePct = parseFloat(raw) || 0;
      }
      return { symbol, price, changePct };
    }
  }
  return null;
}

// Correct exchange codes per US symbol (AAPL is NASDAQ, JPM is NYSE, etc.)
const US_EXCHANGE: Record<string, string> = {
  AAPL: "NASDAQ", MSFT: "NASDAQ", NVDA: "NASDAQ", GOOGL: "NASDAQ",
  GOOG: "NASDAQ", TSLA: "NASDAQ", AMZN: "NASDAQ", META: "NASDAQ",
  AVGO: "NASDAQ", COST: "NASDAQ", PEP: "NASDAQ", CSCO: "NASDAQ",
  AMD: "NASDAQ", ADBE: "NASDAQ", NFLX: "NASDAQ", TXN: "NASDAQ",
  QCOM: "NASDAQ", INTC: "NASDAQ", CMCSA: "NASDAQ", NKE: "NASDAQ",
  ORCL: "NASDAQ", ACN: "NYSE", T: "NYSE", VZ: "NYSE",
  JPM: "NYSE", V: "NYSE", JNJ: "NYSE", WMT: "NYSE", XOM: "NYSE",
  HD: "NYSE", PG: "NYSE", KO: "NYSE", MCD: "NYSE", DIS: "NYSE",
  BA: "NYSE", CAT: "NYSE", CVX: "NYSE", GS: "NYSE", IBM: "NYSE",
  MA: "NYSE", UNH: "NYSE", MRK: "NYSE", ABBV: "NYSE", BAC: "NYSE",
  PFE: "NYSE", TMO: "NYSE", DHR: "NYSE", ABT: "NYSE", WFC: "NYSE",
  "BRK.B": "NYSE", LLY: "NYSE", GE: "NYSE",
};

function googleFinanceUrl(symbol: string, market: string): string {
  if (market === "CRYPTO") {
    return `https://www.google.com/finance/quote/${symbol}-USD`;
  }
  const exchange = US_EXCHANGE[symbol.toUpperCase()] || "NASDAQ";
  return `https://www.google.com/finance/quote/${symbol}:${exchange}`;
}

/**
 * Fetch a quote from Google Finance using plain HTTP + cheerio.
 * Classifies failures (blocked / empty / network) for the self-healing loop.
 */
export async function fetchHttpQuote(
  symbol: string,
  market: string
): Promise<FetchResult> {
  const url = googleFinanceUrl(symbol, market);
  try {
    const res = await axios.get(url, {
      headers: {
        "User-Agent": randomUA(),
        Accept: "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
      },
      timeout: 8000,
    });
    if (res.status === 403 || res.status === 429) {
      return { status: "blocked", error: `HTTP ${res.status}`, source: "http" };
    }
    if (res.status !== 200) {
      return { status: "network_error", error: `HTTP ${res.status}`, source: "http" };
    }
    const quote = parseGoogleFinance(res.data, symbol);
    if (quote) {
      return { status: "ok", quote, source: "http" };
    }
    return { status: "structure_changed", error: "No price found in page", source: "http" };
  } catch (err: unknown) {
    const e = toErrorLike(err);
    if (e.code === "ECONNABORTED") {
      return { status: "timeout", error: "Request timed out", source: "http" };
    }
    const status = e.response?.status;
    if (status === 403 || status === 429) {
      return { status: "blocked", error: `HTTP ${status}`, source: "http" };
    }
    return { status: "network_error", error: e.message || "Network error", source: "http" };
  }
}
