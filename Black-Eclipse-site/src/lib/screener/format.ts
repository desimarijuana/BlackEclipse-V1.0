// Pure formatting helpers for the Market Screener tables.
// Extracted from market-overview.tsx (memory/simplicity standing goal) — these
// are context-free and were only ever re-derived inline.

import { formatPriceWithCurrency } from '@/lib/market-currency';

/** Native-currency price ("PKR 327.43", "CNY 12.40", "$ 189.00"). */
export const priceWithCurrency = (country: string, value: number) =>
  formatPriceWithCurrency(country, value);

// Commodities & forex are ALWAYS shown in US dollars ("$"), per spec.
// Yahoo returns some contracts in US cents (USc/bu, USc/lb) — convert those
// to whole dollars so every price reads as USD. FX pairs are already quoted
// in the pair's units (EURUSD = dollars per euro) so they pass through.
export const COMMODITY_USD_SCALE: Record<string, number> = {
  'ZW=F': 0.01, 'ZC=F': 0.01, 'ZS=F': 0.01, 'KC=F': 0.01,
  'SB=F': 0.01, 'CT=F': 0.01, 'LE=F': 0.01,
};

export const formatUsdPrice = (symbol: string, value: number | null | undefined) => {
  if (value == null || !Number.isFinite(value)) return '-';
  const scaled = value * (COMMODITY_USD_SCALE[symbol] ?? 1);
  return `$ ${scaled.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: Math.abs(scaled) >= 1 ? 2 : 6,
  })}`;
};

/** Human-readable market cap ("2.97T", "412.5B", "18.3M"). */
export const fmtCap = (n?: number | null) => {
  if (!n || n <= 0) return '-';
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  return n.toLocaleString();
};

/** Relative timestamp ("12m ago", "3h ago", "2d ago"). */
export const timeAgo = (iso?: string | Date) => {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 0 || Number.isNaN(diff)) return '';
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};
