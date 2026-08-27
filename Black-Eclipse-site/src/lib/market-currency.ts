// Currency helpers for market instruments — SINGLE SOURCE OF TRUTH lives in
// @/lib/markets; this module adds display formatting on top.
import { MARKET_CURRENCY } from "./markets";

export { MARKET_CURRENCY };

// Reverse map: currency code/symbol → itself (so a code like "PKR" or "$"
// resolves straight through) plus every market id → its display symbol.
const CURRENCY_TO_SYMBOL: Record<string, string> = {};
for (const [marketId, symbol] of Object.entries(MARKET_CURRENCY)) {
  // Market id → its symbol (PK → PKR, US → $, ...).
  CURRENCY_TO_SYMBOL[marketId] = symbol;
  // Currency code/symbol → itself, so callers that already carry the code
  // (e.g. "PKR" or "$") don't fall through to the dollar default.
  if (!CURRENCY_TO_SYMBOL[symbol]) CURRENCY_TO_SYMBOL[symbol] = symbol;
}

/** Display currency symbol for a market id or a currency code (defaults to "$"). */
export function currencyCodeFor(marketIdOrCode: string): string {
  return CURRENCY_TO_SYMBOL[marketIdOrCode] || "$";
}

/**
 * Format a price with its market's currency symbol, e.g. "$ 189.42" or
 * "PKR 412.55". Accepts either a market id ("PK", "US") or an already
 * resolved currency code ("PKR", "$"). Values keep 2 decimals except
 * sub-unit prices (crypto-style), which keep up to 6 significant decimals.
 */
export function formatPriceWithCurrency(marketIdOrCode: string, value: number | null | undefined): string {
  const symbol = currencyCodeFor(marketIdOrCode);
  if (value == null || !Number.isFinite(value)) return `${symbol} —`;
  const formatted =
    Math.abs(value) >= 1
      ? value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  return `${symbol} ${formatted}`;
}
