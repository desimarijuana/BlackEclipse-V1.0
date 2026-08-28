// yfinance bridge fetcher — shells out to scripts/yfinance_bridge.py, which
// batches many symbols over one shared Python yfinance session (fast_info,
// chart endpoint only). This is the PRIMARY quote strategy for stock markets:
// one Python process per batch instead of one HTTP round-trip per symbol.
//
// Zero-config: if Python + yfinance are not available, this returns a
// "network_error" and the adaptive chain falls back to other strategies.

import { execFile } from "child_process";
import { promisify } from "util";
import { existsSync } from "fs";
import path from "path";
import type { FetchResult, Quote } from "../types";
import { toErrorLike } from "../types";

const execFileAsync = promisify(execFile);

const BRIDGE_PATH = path.join(process.cwd(), "scripts", "yfinance_bridge.py");

// Market id → Yahoo ticker suffix. Empty means the symbol is already Yahoo-ready.
// Single source of truth — keep in sync with scripts/yfinance_bridge.py (MARKET_SUFFIX).
export const MARKET_SUFFIX: Record<string, string> = {
  US: "",
  PK: ".PSX",
  IN: ".NS",
  CRYPTO: "-USD",
  CN: ".SS",
  TW: ".TW",
  JP: ".T",
  HK: ".HK",
  KR: ".KS",
  SG: ".SI",
  MY: ".KL",
  AU: ".AX",
  UK: ".L",
  DE: ".DE",
  FR: ".PA",
  NL: ".AS",
  CA: ".TO",
  BR: ".SA",
  MX: ".MX",
  SA: ".SR",
  AE: ".AE",
  ZA: ".JO",
  EG: ".CA",
  NG: ".NG",
  RU: ".ME",
  TR: ".IS",
  ID: ".JK",
  TH: ".BK",
  VN: ".VN",
};

/** Resolve a bare symbol to the full Yahoo ticker for a market. */
export function yahooSymbol(symbol: string, market: string): string {
  const suffix = MARKET_SUFFIX[market] ?? "";
  const sym = symbol.trim();
  // China: 6xxxxx -> Shanghai (.SS), 0/3xxxxx -> Shenzhen (.SZ), 4/8xxxxx -> Beijing (.BJ).
  let resolvedSuffix = suffix;
  if (market === "CN" && /^\d{6}$/.test(sym)) {
    if (sym.startsWith("0") || sym.startsWith("3")) resolvedSuffix = ".SZ";
    else if (sym.startsWith("4") || sym.startsWith("8")) resolvedSuffix = ".BJ";
    else resolvedSuffix = ".SS";
  }
  if (!resolvedSuffix) return sym;
  if (sym.endsWith(resolvedSuffix)) return sym;
  return `${sym}${resolvedSuffix}`;
}

// Cache the availability check so we don't spawn Python on every call.
// A failure is cached too, but with a TTL: a transient probe failure (e.g. a
// Python startup timeout under concurrent spawns) must not permanently
// disable yfinance, yet we also must not re-probe (and pay the spawn cost)
// on every single batch while Python is genuinely missing.
let availabilityCache: boolean | null = null;
let availabilityCheckedAt = 0;
let probeInFlight: Promise<boolean> | null = null;
const AVAILABILITY_TTL_MS = 5 * 60 * 1000;

async function probeYfinance(): Promise<boolean> {
  try {
    await execFileAsync("python", ["-c", "import yfinance"], { timeout: 10000 });
    return true;
  } catch {
    return false;
  }
}

async function isYfinanceAvailable(): Promise<boolean> {
  const fresh = Date.now() - availabilityCheckedAt < AVAILABILITY_TTL_MS;
  if (availabilityCache === true && fresh) return true;
  if (availabilityCache === false && fresh) return false;

  if (!probeInFlight) {
    probeInFlight = probeYfinance().then((ok) => {
      availabilityCache = ok;
      availabilityCheckedAt = Date.now();
      probeInFlight = null;
      return ok;
    });
  }
  return probeInFlight;
}

interface BridgeQuote {
  symbol: string;
  price: number;
  prevClose: number | null;
  changePct: number;
  open: number | null;
  dayHigh: number | null;
  dayLow: number | null;
  volume: number | null;
}

interface BridgeQuotesOutput {
  market?: string;
  quotes?: Record<string, BridgeQuote>;
  history?: Record<string, unknown>;
  error?: string;
}

/**
 * Run the bridge once for a batch of symbols. Returns the raw bridge JSON.
 * Throws on spawn failure / total failure.
 */
export async function fetchYahooBatchRaw(
  symbols: string[],
  market: string,
  interval?: string,
  period?: string
): Promise<BridgeQuotesOutput> {
  const clean = symbols.map((s) => s.trim().toUpperCase()).filter(Boolean);
  if (clean.length === 0) return { quotes: {} };

  const args = [BRIDGE_PATH, market, clean.join(",")];
  // Passing interval/period switches the bridge to its history path
  // (one shared yf.download for all symbols) instead of the quote path.
  if (interval && period) args.push(interval, period);

  const { stdout } = await execFileAsync("python", args, {
    timeout: 60000,
    maxBuffer: 8 * 1024 * 1024,
  });

  const output = stdout.trim();
  const jsonStart = output.indexOf("{");
  const jsonStr = jsonStart >= 0 ? output.slice(jsonStart) : output;
  const data: BridgeQuotesOutput = JSON.parse(jsonStr);

  if (data.error) {
    throw new Error(data.error);
  }
  return data;
}

/**
 * Batch quote fetch for many symbols in one market via the Python bridge.
 * Maps each returned quote into the existing Quote shape.
 */
export async function fetchYahooBatchQuote(
  symbols: string[],
  market: string
): Promise<FetchResult[]> {
  if (!existsSync(BRIDGE_PATH)) {
    return symbols.map(() => ({
      status: "network_error" as const,
      error: "yfinance bridge missing",
      source: "yfinance",
    }));
  }

  if (!(await isYfinanceAvailable())) {
    return symbols.map(() => ({
      status: "network_error" as const,
      error: "yfinance not installed",
      source: "yfinance",
    }));
  }

  try {
    const data = await fetchYahooBatchRaw(symbols, market);
    const quotes = data.quotes || {};
    return symbols.map((symbol) => {
      const ticker = yahooSymbol(symbol, market);
      const q = quotes[ticker] || quotes[symbol];
      if (!q || !(q.price > 0)) {
        return {
          status: "empty" as const,
          error: "no quote for symbol",
          source: "yfinance",
        };
      }
      const quote: Quote = {
        symbol,
        price: q.price,
        changePct: q.changePct ?? 0,
        volume: q.volume ?? undefined,
      };
      return { status: "ok" as const, quote, source: "yfinance" };
    });
  } catch (err: unknown) {
    const e = toErrorLike(err);
    const msg = e.message || "yfinance bridge failed";
    if (/timeout/i.test(msg) || /ETIMEDOUT/i.test(msg)) {
      return symbols.map(() => ({ status: "timeout" as const, error: msg, source: "yfinance" }));
    }
    return symbols.map(() => ({
      status: "network_error" as const,
      error: msg,
      source: "yfinance",
    }));
  }
}

/** Single-symbol convenience wrapper over the batch fetcher. */
export async function fetchYfinanceQuote(
  symbol: string,
  market: string
): Promise<FetchResult> {
  const [result] = await fetchYahooBatchQuote([symbol], market);
  return result || { status: "empty", error: "no result", source: "yfinance" };
}
