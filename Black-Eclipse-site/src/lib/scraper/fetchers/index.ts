// Adaptive fetcher chain — the self-healing escalation:
//   1. yfinance bridge (batched Python session — the PRIMARY strategy)
//   2. cheap HTTP + cheerio
//   3. (crypto) dedicated public endpoint
//   4. browser (playwright) for blocked/JS-rendered sites
// Source health from JDDS is used to skip known-bad strategies.

import type { FetchResult } from "../types";
import { toErrorLike } from "../types";
import { fetchHttpQuote } from "./http";
import { fetchBrowserQuote } from "./browser";
import { fetchCryptoQuote } from "./crypto";
import { fetchScraplingQuote } from "./scrapling";
import { fetchYfinanceQuote } from "./yfinance";
import { prisma } from "@/lib/db";

export type Strategy = "http" | "browser" | "crypto" | "scrapling" | "yfinance";

/**
 * Given a symbol + market, try strategies in order until one succeeds.
 * Health data from JDDS lets us skip sources that have failed recently.
 */
export async function fetchQuoteWithFallback(
  symbol: string,
  market: string
): Promise<FetchResult> {
  // Crypto uses its own endpoint first (dedicated free ticker, no key).
  if (market === "CRYPTO") {
    const cryptoResult = await tryStrategy("crypto", () => fetchCryptoQuote(symbol));
    if (cryptoResult.status === "ok") return cryptoResult;
    // Fall through to web fetch for crypto if the endpoint fails.
  }

  // yfinance bridge (batched, session-reusing) — the primary strategy.
  if (await shouldUseStrategy("yfinance", market)) {
    const yfResult = await tryStrategy("yfinance", () => fetchYfinanceQuote(symbol, market));
    if (yfResult.status === "ok") return yfResult;
  }

  // HTTP + cheerio (cheapest, works on static pages)
  const httpResult = await tryStrategy("http", () => fetchHttpQuote(symbol, market));
  if (httpResult.status === "ok") return httpResult;

  // Scrapling (best anti-bot bypass) — preferred when Python + Scrapling are available.
  if (await shouldUseStrategy("scrapling", market)) {
    const scraplingResult = await tryStrategy("scrapling", () => fetchScraplingQuote(symbol, market));
    if (scraplingResult.status === "ok") return scraplingResult;
  }

  // Browser (playwright) escalation as a final fallback.
  if (await shouldUseStrategy("browser", market)) {
    const browserResult = await tryStrategy("browser", () => fetchBrowserQuote(symbol, market));
    if (browserResult.status === "ok") return browserResult;
  }

  // Return the best failure (http result is usually most informative)
  return httpResult;
}

async function tryStrategy(
  source: string,
  fn: () => Promise<FetchResult>
): Promise<FetchResult> {
  try {
    return await fn();
  } catch (err: unknown) {
    const e = toErrorLike(err);
    return {
      status: "network_error",
      error: e.message || "Strategy failed",
      source,
    };
  }
}

async function shouldUseStrategy(source: string, market: string): Promise<boolean> {
  try {
    const health = await prisma.sourceHealth.findFirst({
      where: { source, market, symbol: "*" },
    });
    // If it failed many times and rarely succeeded, skip it.
    if (health && health.failCount > 3 && health.successCount === 0) {
      return false;
    }
    return true;
  } catch {
    return true;
  }
}
