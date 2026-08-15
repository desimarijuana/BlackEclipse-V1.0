// Browser fetcher — escalates to a headless browser for JS-rendered / blocked sites.
// Playwright is only used when the cheaper HTTP fetcher fails, to save resources.

import type { Browser } from "playwright";
import type { FetchResult, Quote } from "../types";
import { toErrorLike } from "../types";

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
 * Fetch a quote using a headless browser (Playwright).
 * Uses a normal user agent; plays "human-ish" (waits for the price element).
 */
export async function fetchBrowserQuote(
  symbol: string,
  market: string
): Promise<FetchResult> {
  const url = googleFinanceUrl(symbol, market);
  let browser: Browser | undefined;
  try {
    // Lazy import so Playwright isn't loaded unless needed.
    const { chromium } = await import("playwright");
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      userAgent:
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    });
    const page = await context.newPage();
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 20000 });

    // Wait for the price element.
    await page.waitForSelector("div[data-last-price]", { timeout: 10000 });

    const price = await page
      .locator("div[data-last-price]")
      .first()
      .getAttribute("data-last-price")
      .catch(() => null);

    if (price) {
      const p = parseFloat(price);
      if (!isNaN(p) && p > 0) {
        const changeRaw = await page
          .locator("div[data-change-percent]")
          .first()
          .getAttribute("data-change-percent")
          .catch(() => "0");
        const quote: Quote = {
          symbol,
          price: p,
          changePct: parseFloat((changeRaw || "0").replace("%", "")) || 0,
        };
        await browser.close();
        return { status: "ok", quote, source: "browser" };
      }
    }
    await browser.close();
    return { status: "structure_changed", error: "No price found", source: "browser" };
  } catch (err: unknown) {
    const e = toErrorLike(err);
    if (browser) await browser.close().catch(() => {});
    const msg = e.message || "Browser fetch failed";
    if (/timeout/i.test(msg)) {
      return { status: "timeout", error: msg, source: "browser" };
    }
    return { status: "network_error", error: msg, source: "browser" };
  }
}
