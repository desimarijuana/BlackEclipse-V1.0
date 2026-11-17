// ── Symbol universe ─────────────────────────────────────────────────────────
// A trading bot may scan more symbols than it may hold. This module owns the
// honest parts: normalising what the user typed, deciding whether the venue
// actually offers a symbol (EURUSD vs EURUSD.m), and ranking several signals so
// the bot takes the best one instead of the first one in the list.
//
// Nothing here invents a symbol or a score. A caller with no candidates gets an
// empty list and must say so.

import { MAX_SYMBOLS } from "./types";
import type { TradingSignal } from "./types";

export interface TradeCandidate {
  symbol: string;
  /** Higher is better. Must come from a real ranking (screener/strategy). */
  score: number;
  setup?: string;
  source?: string;
}

export interface SymbolEvaluation {
  symbol: string;
  signal: TradingSignal;
  /** Signal strength from the strategy (e.g. distance past the trigger). */
  score: number;
  reason: string;
}

/** Parse a comma/space/newline separated symbol field, or an array. */
export function parseSymbols(input: string | readonly string[]): string[] {
  const raw = Array.isArray(input) ? input : String(input ?? "").split(/[\s,;]+/);
  const seen = new Set<string>();
  const out: string[] = [];
  for (const item of raw) {
    const symbol = String(item ?? "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    // A symbol is letters/digits with optional `.`, `-`, `_` suffixes.
    if (!/^[A-Z0-9][A-Z0-9._\-/]{0,23}$/.test(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
    if (out.length >= MAX_SYMBOLS) break;
  }
  return out;
}

function bare(symbol: string): string {
  return symbol.toUpperCase().replace(/[^A-Z0-9]/g, "");
}

/**
 * Is `symbol` offered by the venue? Brokers suffix instruments (EURUSD.m,
 * XAUUSD_SB, BTCUSD-ECN). A suffix match is accepted only when the remainder is
 * non-numeric, so EURUSD never matches EURUSDT.
 */
export function isSymbolTradable(symbol: string, venueSymbols: readonly string[]): boolean {
  const wanted = bare(symbol);
  if (!wanted) return false;
  for (const offered of venueSymbols) {
    const venue = String(offered ?? "").toUpperCase();
    if (!venue) continue;
    if (venue === symbol.toUpperCase()) return true;
    if (bare(venue) === wanted) return true;
    if (bare(venue).startsWith(wanted)) {
      const remainder = venue.slice(symbol.length);
      if (/^[.\-_][A-Z]{1,6}$/i.test(remainder)) return true;
    }
  }
  return false;
}

export interface TradableResolution {
  tradable: string[];
  missing: string[];
  /** Strategy symbol → the venue's own spelling. */
  mapping: Record<string, string>;
}

/** Resolve a strategy's symbols against the venue's instrument list. */
export function resolveTradable(
  symbols: readonly string[],
  venueSymbols: readonly string[],
): TradableResolution {
  const tradable: string[] = [];
  const missing: string[] = [];
  const mapping: Record<string, string> = {};
  for (const symbol of parseSymbols(symbols)) {
    const match = venueSymbols.find((offered) => isSymbolTradable(symbol, [offered]));
    if (match) {
      tradable.push(symbol);
      mapping[symbol] = String(match);
    } else {
      missing.push(symbol);
    }
  }
  return { tradable, missing, mapping };
}

/**
 * Map a "find trades" result onto candidates. The adapter is deliberately
 * tolerant about field names and strict about values: a row without a symbol is
 * dropped, never guessed.
 */
export function candidatesFromFindTrades(
  rows: readonly Record<string, unknown>[],
  source = "find-trades",
): TradeCandidate[] {
  const out: TradeCandidate[] = [];
  for (const row of rows) {
    const symbol = parseSymbols(
      String(row.symbol ?? row.ticker ?? row.instrument ?? ""),
    )[0];
    if (!symbol) continue;
    const scoreRaw =
      row.score ?? row.rank ?? row.confidence ?? row.strength ?? row.edge ?? 0;
    const score = Number(scoreRaw);
    out.push({
      symbol,
      score: Number.isFinite(score) ? score : 0,
      setup:
        typeof row.setup === "string"
          ? row.setup
          : typeof row.pattern === "string"
            ? row.pattern
            : undefined,
      source,
    });
  }
  return dedupeCandidates(out);
}

export function dedupeCandidates(candidates: readonly TradeCandidate[]): TradeCandidate[] {
  const best = new Map<string, TradeCandidate>();
  for (const candidate of candidates) {
    const symbol = parseSymbols(candidate.symbol)[0];
    if (!symbol) continue;
    const existing = best.get(symbol);
    if (!existing || candidate.score > existing.score) {
      best.set(symbol, { ...candidate, symbol });
    }
  }
  return Array.from(best.values()).sort((a, b) => b.score - a.score);
}

/**
 * The universe a bot should scan. Order is deliberate:
 *   1. symbols the operator pinned explicitly;
 *   2. discovered candidates (best score first);
 *   3. never a symbol outside `allowed` (a strategy's own universe);
 *   4. never more than `max`.
 */
export function pickUniverse(input: {
  pinned: readonly string[];
  candidates?: readonly TradeCandidate[];
  allowed?: readonly string[] | null;
  excluded?: readonly string[];
  max?: number;
}): string[] {
  const cap = Math.max(1, Math.min(MAX_SYMBOLS, input.max ?? MAX_SYMBOLS));
  const excluded = new Set(parseSymbols(input.excluded ?? []));
  const allowed = input.allowed ? new Set(parseSymbols(input.allowed)) : null;
  const keep = (symbol: string) =>
    !excluded.has(symbol) && (!allowed || allowed.has(symbol));

  const out: string[] = [];
  const push = (symbol: string) => {
    if (out.length >= cap) return;
    if (!keep(symbol) || out.includes(symbol)) return;
    out.push(symbol);
  };

  for (const symbol of parseSymbols(input.pinned)) push(symbol);
  for (const candidate of dedupeCandidates(input.candidates ?? [])) {
    push(candidate.symbol);
  }
  return out;
}

function isEntry(signal: TradingSignal): boolean {
  return signal === "long_entry" || signal === "short_entry";
}

function isExit(signal: TradingSignal): boolean {
  return signal === "long_exit" || signal === "short_exit";
}

/**
 * Rank several symbol evaluations for one run.
 *
 * Exits always come first (risk-reducing, and they free a slot). Entries are
 * ranked by score. Symbols already held are skipped for entries so a scan can
 * never stack a second position on the same instrument.
 */
export function rankEvaluations(
  evaluations: readonly SymbolEvaluation[],
  options: { openSymbols?: readonly string[]; maxPositions?: number } = {},
): SymbolEvaluation[] {
  const open = new Set(parseSymbols(options.openSymbols ?? []));
  const ranked = [...evaluations].sort((a, b) => {
    const aExit = isExit(a.signal) ? 0 : 1;
    const bExit = isExit(b.signal) ? 0 : 1;
    if (aExit !== bExit) return aExit - bExit;
    return b.score - a.score;
  });
  const limit = options.maxPositions ?? 1;
  const picked: SymbolEvaluation[] = [];
  let entries = 0;
  for (const item of ranked) {
    if (isExit(item.signal)) {
      picked.push(item);
      continue;
    }
    if (!isEntry(item.signal)) continue;
    if (open.has(item.symbol)) continue;
    if (entries >= limit) continue;
    entries += 1;
    picked.push(item);
  }
  // Keep the no-signal rows out of the execution list but let callers explain
  // them: `rankEvaluations` returns only actionable items.
  return picked;
}

/** A compact summary for the decision record's `reason` on a multi-symbol scan. */
export function describeScan(
  scanned: readonly string[],
  picked: readonly SymbolEvaluation[],
): string {
  if (!scanned.length) return "No symbols to scan.";
  if (!picked.length) return `Scanned ${scanned.length} symbol(s): no actionable signal.`;
  const names = picked.map((item) => `${item.symbol} ${item.signal}`).join(", ");
  return `Scanned ${scanned.length} symbol(s); acting on ${names}.`;
}
