// ── Data preflight ──────────────────────────────────────────────────────────
// A backtest can fail for a boring reason: there are no bars for the symbol at
// the requested interval. The studio used to discover that only after a run.
// This module turns the runtime's stored-series catalogue into a plain-language
// coverage answer BEFORE the run.
//
// It reads only what the runtime reports. A symbol that is absent from the
// stored catalogue is not declared impossible — the engine may still fetch it
// from a configured provider — so the state is "not in the stored catalogue",
// never "there is no data".

export interface StoredSeriesLike {
  symbol: string;
  interval: string;
  adjusted?: number | boolean;
  provider?: string;
  n?: number;
  start?: string | null;
  end?: string | null;
}

export type SeriesCoverageState = "ready" | "missing";

export interface SymbolCoverage {
  symbol: string;
  state: SeriesCoverageState;
  match?: StoredSeriesLike;
  /** Other intervals stored for the same instrument, most bars first. */
  alternatives: StoredSeriesLike[];
}

export type CoverageState = "ready" | "partial" | "missing" | "unknown";

export interface CoverageResult {
  state: CoverageState;
  interval: string;
  symbols: SymbolCoverage[];
  headline: string;
  detail: string;
}

/** `btc-usd`, `BTC/USD`, `BTCUSD` all identify the same instrument. */
export function normalizeSymbol(symbol: string): string {
  return symbol.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
}

export function splitSymbols(input: string): string[] {
  return input
    .split(",")
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
}

function barsOf(series: StoredSeriesLike): number {
  return typeof series.n === "number" && Number.isFinite(series.n) ? series.n : 0;
}

function rangeOf(series: StoredSeriesLike): string {
  if (!series.start || !series.end) return "";
  return `${series.start.slice(0, 10)} → ${series.end.slice(0, 10)}`;
}

function describeMatch(series: StoredSeriesLike | undefined): string {
  if (!series) return "";
  const parts = [`${barsOf(series).toLocaleString()} bars`];
  const range = rangeOf(series);
  if (range) parts.push(range);
  if (series.provider) parts.push(`via ${series.provider}`);
  return parts.join(" · ");
}

/**
 * Match every requested symbol against the stored catalogue at one interval.
 * `series` is `null` when the catalogue could not be read, which is a distinct
 * "we do not know" answer rather than a "no data" answer.
 */
export function evaluateCoverage(
  series: StoredSeriesLike[] | null,
  symbols: string[],
  interval: string,
): CoverageResult {
  const wanted = interval.trim() || "1d";
  if (!symbols.length) {
    return {
      state: "unknown",
      interval: wanted,
      symbols: [],
      headline: "Enter at least one symbol to check data coverage.",
      detail: "",
    };
  }
  if (series === null) {
    return {
      state: "unknown",
      interval: wanted,
      symbols: [],
      headline: "The stored data catalogue could not be read.",
      detail: "The run may still work if a configured provider can serve the symbol.",
    };
  }

  const normalized = series.map((item) => ({ item, key: normalizeSymbol(item.symbol) }));
  const matches: SymbolCoverage[] = symbols.map((symbol) => {
    const key = normalizeSymbol(symbol);
    const forSymbol = normalized.filter((entry) => entry.key === key);
    const exact = forSymbol.find((entry) => entry.item.interval.trim().toLowerCase() === wanted.toLowerCase());
    const alternatives = forSymbol
      .filter((entry) => entry !== exact)
      .map((entry) => entry.item)
      .sort((a, b) => barsOf(b) - barsOf(a));
    return {
      symbol,
      state: exact ? "ready" : "missing",
      match: exact?.item,
      alternatives,
    };
  });

  const ready = matches.filter((item) => item.state === "ready");
  const state: CoverageState = ready.length === matches.length ? "ready" : ready.length === 0 ? "missing" : "partial";

  const headline =
    state === "ready"
      ? `${matches.length === 1 ? "Bars found" : `Bars found for all ${matches.length} symbols`} at ${wanted}.`
      : state === "partial"
        ? `${ready.length} of ${matches.length} symbols have stored ${wanted} bars.`
        : `No stored ${wanted} bars for the requested symbol${matches.length === 1 ? "" : "s"}.`;

  const detail =
    state === "ready"
      ? matches.map((item) => `${item.symbol}: ${describeMatch(item.match)}`).join(" • ")
      : matches
          .map((item) => {
            if (item.state === "ready") return `${item.symbol}: ${describeMatch(item.match)}`;
            const hint = item.alternatives.length
              ? `stored intervals: ${item.alternatives.map((alt) => alt.interval).join(", ")}`
              : "not in the stored catalogue";
            return `${item.symbol}: ${hint}`;
          })
          .join(" • ");

  return { state, interval: wanted, symbols: matches, headline, detail };
}
