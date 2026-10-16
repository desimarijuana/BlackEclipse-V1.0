// Data feeds for the alert engine — snapshot quotes (TradingView scan or the
// yfinance bridge) plus the candle cache used by indicator conditions.
//
// Snapshot-only watches (price / change% / volume / marketCap / PE / EPS)
// never touch the candle cache. Candle watches update the cache from the
// yfinance bridge's OHLC path, batched in chunks of ~50 symbols.

import { prisma } from "@/lib/db";
import { getCachedMarketScan } from "@/lib/scraper/fetchers/tradingview";
import {
  fetchYahooBatchRaw,
  yahooSymbol,
} from "@/lib/scraper/fetchers/yfinance";
import { operandKey, needsCandles, type ConditionNode } from "./conditionEvaluator";

export interface SnapshotWindow {
  close: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  changePct: number;
  marketCap: number;
  pe: number;
  eps: number;
  sector: number; // hashed — SECTOR equality compares the hash
}

export const MAX_CANDLE_CHUNK = 50;
export const MIN_INTERVAL_SEC = 30;

export type AlertDataSource = "Auto" | "TradingView" | "yfinance";

/** Normalize the stored `dataSource` to a known value (default Auto). */
export function normalizeDataSource(value: string | null | undefined): AlertDataSource {
  const v = (value ?? "").trim().toLowerCase();
  if (v === "tradingview" || v === "tv") return "TradingView";
  if (v === "yfinance" || v === "yahoo") return "yfinance";
  return "Auto";
}

/** Map an alert's symbols/market to TradingView scan rows + yfinance quotes. */
export interface SymbolSnapshot {
  symbol: string;
  close?: number;
  open?: number;
  high?: number;
  low?: number;
  volume?: number;
  changePct?: number;
  marketCap?: number;
  peRatio?: number;
  eps?: number;
  sector?: string | null;
}

export function chunk<T>(arr: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += size) out.push(arr.slice(i, i + size));
  return out;
}

/**
 * Fetch snapshots for a set of symbols in one market.
 *
 * `dataSource` (from the watch config) selects the source:
 *   * `Auto` (default) — the cached TradingView scan, then the yfinance bridge
 *     for symbols TradingView does not cover.
 *   * `TradingView` — ONLY the cached scan (no bridge fallback).
 *   * `yfinance` — ONLY the bridge.
 * A source that returns nothing leaves the symbol out (honest "no data"),
 * never a fabricated quote.
 */
export async function fetchSnapshots(
  market: string,
  symbols: string[],
  dataSource: string | null = "Auto"
): Promise<Map<string, SymbolSnapshot>> {
  const out = new Map<string, SymbolSnapshot>();
  if (symbols.length === 0) return out;
  const source = normalizeDataSource(dataSource);
  const useTradingView = source !== "yfinance";
  const useYfinance = source !== "TradingView";

  let scanRows: import("@/lib/scraper/types").ScanRow[] = [];
  if (useTradingView) {
    try {
      scanRows = await getCachedMarketScan(market);
    } catch {
      scanRows = [];
    }
  }
  const bySymbol = new Map(scanRows.map((r) => [r.symbol, r]));

  const missing = useYfinance ? symbols.filter((s) => !bySymbol.has(s)) : [];
  if (missing.length > 0) {
    for (const batch of chunk(missing, MAX_CANDLE_CHUNK)) {
      try {
        const raw = await fetchYahooBatchRaw(batch, market);
        const quotes = raw.quotes || {};
        for (const sym of batch) {
          const q = quotes[yahooSymbol(sym, market)] || quotes[sym];
          if (q && q.price > 0) {
            bySymbol.set(sym, {
              symbol: sym,
              exchange: "",
              name: sym,
              price: q.price,
              changePct: q.changePct ?? 0,
              volume: q.volume ?? undefined,
              fiftyTwoWeekHigh: q.dayHigh ?? undefined,
              fiftyTwoWeekLow: q.dayLow ?? undefined,
              yahooSymbol: yahooSymbol(sym, market),
            });
          }
        }
      } catch {
        // batch failed (no python, rate limit) — leave those symbols missing
      }
    }
  }

  for (const sym of symbols) {
    const r = bySymbol.get(sym);
    if (!r) continue;
    // Zero/negative LTP never enters evaluation — poisons ratio indicators.
    if (!(r.price > 0)) continue;
    out.set(sym, {
      symbol: sym,
      close: r.price,
      volume: r.volume,
      changePct: r.changePct,
      marketCap: r.marketCap,
      peRatio: r.peRatio,
      eps: r.eps,
      sector: r.sector,
    });
  }
  return out;
}

/**
 * Build the SeriesMap for snapshot indicators from one symbol's snapshot.
 * Values are single-sample series (offset reads beyond 0 → NaN → failed).
 */
export function snapshotWindow(snap: SymbolSnapshot): Map<string, number[]> {
  const w = new Map<string, number[]>();
  const put = (k: string, v: number | undefined) => {
    if (typeof v === "number" && Number.isFinite(v)) w.set(k, [v]);
  };
  put(operandKey("CLOSE"), snap.close);
  put(operandKey("OPEN"), snap.open);
  put(operandKey("HIGH"), snap.high);
  put(operandKey("LOW"), snap.low);
  put(operandKey("VOLUME"), snap.volume);
  put(operandKey("CHANGE_PCT"), snap.changePct);
  put(operandKey("MARKET_CAP"), snap.marketCap);
  put(operandKey("PE"), snap.peRatio);
  put(operandKey("EPS"), snap.eps);
  if (snap.sector) {
    // SECTOR is a string; hash it so == comparisons work numerically.
    let h = 0;
    for (let i = 0; i < snap.sector.length; i++) {
      h = (h * 31 + snap.sector.charCodeAt(i)) | 0;
    }
    w.set(operandKey("SECTOR"), [h]);
  }
  return w;
}

/** Collect every indicator series key a condition tree references. */
export function referencedIndicators(conditions: unknown): string[] {
  const found = new Set<string>();
  const walk = (node: unknown) => {
    if (Array.isArray(node)) return node.forEach(walk);
    if (!node || typeof node !== "object") return;
    const n = node as ConditionNode & { children?: unknown[] };
    if ("children" in n && Array.isArray(n.children)) return n.children.forEach(walk);
    const leaf = node as { indicator?: string; compareIndicator?: string };
    if (leaf.indicator) found.add(leaf.indicator);
    if (leaf.compareIndicator) found.add(leaf.compareIndicator);
  };
  walk(conditions);
  return [...found];
}

const YF_INTERVAL: Record<string, string> = {
  "1m": "1m",
  "5m": "5m",
  "15m": "15m",
  "1h": "60m",
  "1d": "1d",
};

export interface Candle {
  ts: Date;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number | null;
}

/**
 * Update the candle cache for a set of symbols on one timeframe via the
 * yfinance bridge's OHLC path (one shared yf.download per chunk of ≤50).
 * Rejects zero/negative closes (they poison ratio indicators → Infinity).
 */
export async function updateCandleCache(
  market: string,
  symbols: string[],
  timeframe: string,
  lookback = 60
): Promise<number> {
  const interval = YF_INTERVAL[timeframe] ?? "1d";
  const periodMap: Record<string, string> = {
    "1m": "5d",
    "5m": "1mo",
    "15m": "1mo",
    "1h": "3mo",
    "1d": "6mo",
  };
  const period = periodMap[timeframe] ?? "6mo";
  let written = 0;

  for (const batch of chunk(symbols, MAX_CANDLE_CHUNK)) {
    try {
      const raw = await fetchYahooBatchRaw(batch, market, interval, period);
      // The Python bridge emits `date` (a 'YYYY-MM-DD' string). `ts` is also
      // accepted for forward-compat, but reading ONLY `ts` silently stamped
      // every bar with `new Date()` — collapsing a whole series onto one
      // timestamp so the composite-key upsert overwrote it down to a single
      // row. That bug made candle indicators (and Investor Eye analogues)
      // permanently "warming".
      const history = (raw.history || {}) as Record<
        string,
        Array<{ date?: string; ts?: string | number; open?: number; high?: number; low?: number; close?: number; volume?: number }>
      >;
      const rows: Array<{
        symbol: string; timeframe: string; ts: Date;
        o: number; h: number; l: number; c: number; v: number | null;
      }> = [];
      for (const sym of symbols) {
        const ticker = yahooSymbol(sym, market);
        const rowsIn = history[ticker] || history[sym] || [];
        for (const r of rowsIn.slice(-lookback)) {
          const c = Number(r.close);
          const o = Number(r.open);
          const h = Number(r.high);
          const l = Number(r.low);
          // Zero/negative LTP must never enter the buffer.
          if (!(c > 0) || !(o > 0) || !(h > 0) || !(l > 0)) continue;
          if (!Number.isFinite(c) || !Number.isFinite(o) || !Number.isFinite(h) || !Number.isFinite(l)) continue;
          // Prefer the bar's own date. A missing/unparseable date is SKIPPED
          // rather than defaulted to `now` — silently misdating history is worse
          // than dropping one bar.
          const rawDate = r.date ?? r.ts;
          if (rawDate === undefined || rawDate === null || rawDate === "") continue;
          const ts = new Date(rawDate);
          if (Number.isNaN(ts.getTime())) continue;
          rows.push({
            symbol: sym, timeframe, ts,
            o, h, l, c,
            v: typeof r.volume === "number" && Number.isFinite(r.volume) ? r.volume : null,
          });
        }
      }
      if (rows.length > 0) {
        for (const r of rows) {
          // skipDuplicates via per-row upsert on the composite key
          await prisma.candles.upsert({
            where: { symbol_timeframe_ts: { symbol: r.symbol, timeframe: r.timeframe, ts: r.ts } },
            create: r,
            update: { o: r.o, h: r.h, l: r.l, c: r.c, v: r.v },
          });
          written++;
        }
      }
    } catch {
      // batch failed — candle indicators report warming for these symbols
    }
  }
  return written;
}

/**
 * Load indicator series for one symbol from the candle cache, newest-last,
 * computing SMA/EMA/RSI on top of the raw closes. Returns the series window
 * for the evaluator (candle pseudo-indicators + snapshot passthrough).
 */
export async function indicatorWindow(
  symbol: string,
  timeframe: string,
  conditions: unknown
): Promise<Map<string, number[]>> {
  const window = new Map<string, number[]>();
  const needed = referencedIndicators(conditions);
  // OPEN/HIGH/LOW live in the candle cache (the TradingView scan row carries no
  // OHL), so they count as candle-backed data alongside SMA/EMA/RSI.
  const ohl = new Set(needed.filter((i) => i === "OPEN" || i === "HIGH" || i === "LOW"));
  const candleInds = needed.filter((i) => i !== "CLOSE" && !["OPEN", "HIGH", "LOW", "VOLUME", "CHANGE_PCT", "MARKET_CAP", "PE", "EPS", "SECTOR"].includes(i));
  if (candleInds.length === 0 && ohl.size === 0 && !needsCandles(conditions)) return window;

  const rows = await prisma.candles.findMany({
    where: { symbol, timeframe },
    orderBy: { ts: "asc" },
  });
  if (rows.length === 0) return window;

  const closes = rows.map((r) => r.c);
  window.set(operandKey("CLOSE"), [...closes]);
  if (ohl.has("OPEN")) window.set(operandKey("OPEN"), rows.map((r) => r.o));
  if (ohl.has("HIGH")) window.set(operandKey("HIGH"), rows.map((r) => r.h));
  if (ohl.has("LOW")) window.set(operandKey("LOW"), rows.map((r) => r.l));

  for (const ind of candleInds) {
    const m = /^([A-Z]+)(?:\((\{.*\})\))?$/.exec(ind);
    if (!m) continue;
    const name = m[1];
    let params: Record<string, number> = {};
    if (m[2]) {
      try {
        params = JSON.parse(m[2].replace(/'/g, '"'));
      } catch {
        params = {};
      }
    }
    const n = Math.max(2, Math.min(400, Math.floor(params.n ?? 14)));
    if (name === "SMA") window.set(operandKey("SMA", { n }), sma(closes, n));
    else if (name === "EMA") window.set(operandKey("EMA", { n }), ema(closes, n));
    else if (name === "RSI") window.set(operandKey("RSI", { n }), rsi(closes, n));
  }
  return window;
}

export function sma(values: number[], n: number): number[] {
  const out: number[] = [];
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    sum += values[i];
    if (i >= n) sum -= values[i - n];
    out.push(i >= n - 1 ? sum / n : NaN);
  }
  return out;
}

export function ema(values: number[], n: number): number[] {
  const k = 2 / (n + 1);
  const out: number[] = [];
  let prev = NaN;
  for (let i = 0; i < values.length; i++) {
    if (i === n - 1) {
      prev = values.slice(0, n).reduce((a, b) => a + b, 0) / n;
    } else if (i >= n) {
      prev = values[i] * k + prev * (1 - k);
    }
    out.push(i >= n - 1 ? prev : NaN);
  }
  return out;
}

export function rsi(values: number[], n = 14): number[] {
  const out: number[] = new Array(values.length).fill(NaN);
  if (values.length <= n) return out;
  let gain = 0;
  let loss = 0;
  for (let i = 1; i <= n; i++) {
    const d = values[i] - values[i - 1];
    if (d >= 0) gain += d;
    else loss -= d;
  }
  let avgGain = gain / n;
  let avgLoss = loss / n;
  out[n] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  for (let i = n + 1; i < values.length; i++) {
    const d = values[i] - values[i - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    avgGain = (avgGain * (n - 1) + g) / n;
    avgLoss = (avgLoss * (n - 1) + l) / n;
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss);
  }
  return out;
}

/**
 * Warmup check: does the candle cache hold enough bars for the deepest
 * offset/cross requirement in the tree?
 */
export async function hasWarmupBars(
  symbol: string,
  timeframe: string,
  conditions: unknown,
  minBars = 3
): Promise<boolean> {
  if (!needsCandles(conditions)) return true;
  const count = await prisma.candles.count({ where: { symbol, timeframe } });
  return count >= minBars;
}