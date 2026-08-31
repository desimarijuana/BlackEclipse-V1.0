// Display-currency layer — the standard "compute in one base (USD), convert
// at the presentation layer" pattern. The portfolio engine always aggregates
// in USD; this module converts engine output to the user's chosen display
// currency and formats it with the Intl.NumberFormat standard.
//
// FX rates come from /api/forex (Yahoo-backed USD→X pairs). A localStorage
// snapshot keeps the UI working when the endpoint is slow/offline.

'use client';

export type Currency = string; // ISO 4217 code (USD, PKR, EUR, ...)

// Currencies offered in Settings. All have USD→X pairs in /api/forex.
export const DISPLAY_CURRENCIES: Array<{ code: Currency; label: string }> = [
  { code: 'USD', label: 'US Dollar' },
  { code: 'PKR', label: 'Pakistani Rupee' },
  { code: 'EUR', label: 'Euro' },
  { code: 'GBP', label: 'British Pound' },
  { code: 'INR', label: 'Indian Rupee' },
  { code: 'JPY', label: 'Japanese Yen' },
  { code: 'AED', label: 'UAE Dirham' },
  { code: 'SAR', label: 'Saudi Riyal' },
  { code: 'CAD', label: 'Canadian Dollar' },
  { code: 'AUD', label: 'Australian Dollar' },
  { code: 'CHF', label: 'Swiss Franc' },
  { code: 'CNY', label: 'Chinese Yuan' },
  { code: 'SGD', label: 'Singapore Dollar' },
  { code: 'TRY', label: 'Turkish Lira' },
];

const STORAGE_KEY = 'eclipse_display_currency';

/** Default from the browser locale (en-PK → PKR, en-IN → INR, ...), else USD. */
export function localeDefaultCurrency(): Currency {
  if (typeof navigator === 'undefined') return 'USD';
  try {
    const locale = navigator.language || 'en-US';
    const region = (locale.split('-')[1] || '').toUpperCase();
    const map: Record<string, Currency> = {
      PK: 'PKR', IN: 'INR', GB: 'GBP', JP: 'JPY', AE: 'AED', SA: 'SAR',
      CA: 'CAD', AU: 'AUD', CH: 'CHF', CN: 'CNY', SG: 'SGD', TR: 'TRY',
      DE: 'EUR', FR: 'EUR', ES: 'EUR', IT: 'EUR', NL: 'EUR', IE: 'EUR',
    };
    if (region && map[region]) return map[region];
    if (['EUR', 'GBP', ...Object.keys(map)].length && region === '' && locale.startsWith('en')) return 'USD';
  } catch { /* fall through */ }
  return 'USD';
}

export function getDisplayCurrency(): Currency {
  if (typeof window === 'undefined') return 'USD';
  try {
    return localStorage.getItem(STORAGE_KEY) || localeDefaultCurrency();
  } catch {
    return 'USD';
  }
}

export function setDisplayCurrency(code: Currency) {
  try {
    localStorage.setItem(STORAGE_KEY, code);
    window.dispatchEvent(new CustomEvent('eclipse:currency-change', { detail: code }));
  } catch { /* private mode — in-memory only */ }
}

/** USD → display-currency rate derived from /api/forex pairs. */
export function rateFromPairs(pairs: Array<{ base: string; quote: string; price: number; found: boolean }>, target: Currency): number {
  if (target === 'USD') return 1;
  const pair = pairs.find(p => p.base === 'USD' && p.quote === target && p.found && p.price > 0);
  return pair ? pair.price : 0; // 0 = unknown → callers fall back to USD
}

export interface FxState {
  /** Map of currency code → USD→X rate (USD = 1). */
  rates: Record<string, number>;
  /** ISO timestamp of the rate snapshot. */
  asOf: string | null;
}

/** Fetch the FX matrix (cached 5 min in localStorage as last-known-good). */
export async function fetchFxMatrix(): Promise<FxState> {
  const LS_CACHE = 'eclipse_fx_matrix';
  const TTL = 5 * 60 * 1000;
  try {
    const cached = localStorage.getItem(LS_CACHE);
    if (cached) {
      const p = JSON.parse(cached) as { t: number; rates: Record<string, number>; asOf: string };
      if (Date.now() - p.t < TTL && p.rates) {
        return { rates: p.rates, asOf: p.asOf };
      }
    }
  } catch { /* ignore */ }

  try {
    const res = await fetch('/api/forex', { signal: AbortSignal.timeout(8000) });
    const data = await res.json();
    const rates: Record<string, number> = { USD: 1 };
    for (const p of (data.pairs ?? []) as Array<{ base: string; quote: string; price: number; found: boolean }>) {
      if (p.base === 'USD' && p.found && p.price > 0) rates[p.quote] = p.price;
    }
    const asOf = new Date().toISOString();
    if (Object.keys(rates).length > 1) {
      try { localStorage.setItem(LS_CACHE, JSON.stringify({ t: Date.now(), rates, asOf })); } catch { /* ignore */ }
      return { rates, asOf };
    }
  } catch { /* fall through to cached */ }

  // Last-known-good fallback.
  try {
    const cached = localStorage.getItem(LS_CACHE);
    if (cached) {
      const p = JSON.parse(cached) as { rates: Record<string, number>; asOf: string };
      return { rates: p.rates, asOf: p.asOf };
    }
  } catch { /* ignore */ }
  return { rates: { USD: 1 }, asOf: null };
}

/** Convert a USD amount into the display currency (0 rate → returns USD amount). */
export function convertFromUsd(usdAmount: number, currency: Currency, rates: Record<string, number>): number {
  if (currency === 'USD') return usdAmount;
  const r = rates[currency];
  return r && r > 0 ? usdAmount * r : usdAmount;
}

/**
 * Format an amount already denominated in `currency` using Intl.
 * Zero-decimal currencies (JPY, KRW, VND, IDR) are handled by Intl itself.
 */
export function fmtMoney(amount: number, currency: Currency, dp = 2): string {
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: dp,
      maximumFractionDigits: dp,
    }).format(amount);
  } catch {
    // Unknown code → fall back to a code-prefixed number.
    return `${currency} ${amount.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`;
  }
}

/** Compact formatter for charts/KPI tiles ($1.2M → ₨338M style). */
export function fmtMoneyCompact(amount: number, currency: Currency): string {
  const a = Math.abs(amount);
  const sign = amount < 0 ? '-' : '';
  try {
    if (a >= 1e9) return `${sign}${fmtMoneyShort(a / 1e9)}B`;
    if (a >= 1e6) return `${sign}${fmtMoneyShort(a / 1e6)}M`;
    if (a >= 1000) return `${sign}${fmtMoneyShort(a / 1e3)}k`;
    return fmtMoney(amount, currency, a >= 100 ? 0 : 2);
  } catch {
    return fmtMoney(amount, currency, 2);
  }
}
function fmtMoneyShort(n: number): string {
  return n >= 100 ? n.toFixed(0) : n >= 10 ? n.toFixed(1) : n.toFixed(2);
}