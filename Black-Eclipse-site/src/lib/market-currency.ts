// Currency helpers for market instruments — SINGLE SOURCE OF TRUTH lives in
// @/lib/markets; this module adds display formatting on top.
import { MARKET_CURRENCY } from "./markets";

export { MARKET_CURRENCY };

/** Display currency symbol for a market id (defaults to USD "$"). */
export function currencyCodeFor(marketId: string): string {
  return MARKET_CURRENCY[marketId] || "$";
}

/**
 * Format a price with its market's currency symbol, e.g. "$ 189.42" or
 * "₨ 412.55". Values keep 2 decimals except sub-unit prices (crypto-style),
 * which keep up to 6 significant decimals.
 */
export function formatPriceWithCurrency(marketId: string, value: number | null | undefined): string {
  const symbol = currencyCodeFor(marketId);
  if (value == null || !Number.isFinite(value)) return `${symbol} —`;
  const formatted =
    Math.abs(value) >= 1
      ? value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
      : value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 6 });
  return `${symbol} ${formatted}`;
}
