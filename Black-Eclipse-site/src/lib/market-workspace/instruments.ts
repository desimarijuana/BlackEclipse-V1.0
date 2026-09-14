// ── Instrument metadata + formatting ─────────────────────────────────────────
// The single client-side source of truth for how an instrument's price/change/
// volume is DISPLAYED. Formatting is derived from the instrument's market —
// currency, exchange, timezone, decimal precision — never hardcoded per symbol.
//
// Market metadata (currency / exchange / timezone) lives in @/lib/scraper/markets
// (JDDS seeds) and @/lib/markets; this module layers display rules on top so a
// chart panel, watchlist row, and fundamentals table all render identically.

import { MARKET_CURRENCY, MARKET_FULL_NAME, toMarketId } from '@/lib/markets';
import { MARKET_SEEDS } from '@/lib/scraper/markets';

/** Everything we know about an instrument's market + display rules. */
export interface InstrumentMeta {
  symbol: string;
  market: string;
  name?: string;
  /** ISO 4217-ish code or symbol shown before the price ("$", "PKR", "₹"). */
  currency: string;
  /** Full currency code for labels/headers ("USD", "PKR", "INR"). */
  currencyCode: string;
  exchange: string;
  timezone: string;
  /** Number of decimals this market's prices display by default. */
  decimals: number;
  /** Human-readable market/country name. */
  marketName: string;
  /** True when the market never closes (crypto). */
  isCrypto: boolean;
  /** True when quotes are USD-denominated. */
  isUsd: boolean;
}

// Native currency symbols for the markets BlackEclipse ships. Falls back to the
// MARKET_CURRENCY map (which stores short display symbols).
const CURRENCY_SYMBOL: Record<string, string> = {
  USD: '$', PKR: 'PKR', INR: '₹', CNY: '¥', TWD: 'NT$', HKD: 'HK$', JPY: '¥',
  KRW: '₩', SGD: 'S$', MYR: 'RM', AUD: 'A$', GBP: '£', EUR: '€', CAD: 'C$',
  BRL: 'R$', MXN: 'MX$', SAR: 'SAR', AED: 'AED', ZAR: 'R', EGP: 'E£',
  NGN: '₦', RUB: '₽', TRY: '₺', IDR: 'Rp', THB: '฿', VND: '₫',
};

// Market → ISO currency code, derived from the display currency in markets.ts.
const CURRENCY_CODE: Record<string, string> = {
  US: 'USD', CRYPTO: 'USD', PK: 'PKR', IN: 'INR', CN: 'CNY', TW: 'TWD',
  HK: 'HKD', JP: 'JPY', KR: 'KRW', SG: 'SGD', MY: 'MYR', AU: 'AUD', UK: 'GBP',
  DE: 'EUR', FR: 'EUR', NL: 'EUR', CA: 'CAD', BR: 'BRL', MX: 'MXN', SA: 'SAR',
  AE: 'AED', ZA: 'ZAR', EG: 'EGP', NG: 'NGN', RU: 'RUB', TR: 'TRY', ID: 'IDR',
  TH: 'THB', VN: 'VND',
};

// Exchange + timezone come from the scrape seeds for the markets we trade.
const SEED_BY_MARKET: Record<string, { exchange: string; timezone: string; isCrypto: boolean }> = {};
for (const seed of MARKET_SEEDS) {
  SEED_BY_MARKET[seed.id] = { exchange: seed.exchange, timezone: seed.timezone, isCrypto: seed.isCrypto };
}

// Extra markets known to the app but not in the scrape seeds (still tradable /
// searchable in JDDS). Exchange labels follow the primary listing venue.
const EXTRA_EXCHANGE: Record<string, string> = {
  CN: 'SSE/SZSE', TW: 'TWSE', HK: 'HKEX', JP: 'TSE', KR: 'KRX', SG: 'SGX',
  MY: 'Bursa', AU: 'ASX', UK: 'LSE', DE: 'XETRA', FR: 'Euronext', NL: 'Euronext',
  CA: 'TSX', BR: 'B3', MX: 'BMV', SA: 'Tadawul', AE: 'DFM', ZA: 'JSE',
  EG: 'EGX', NG: 'NGX', RU: 'MOEX', TR: 'BIST', ID: 'IDX', TH: 'SET', VN: 'HOSE',
  FOREX: 'FX', COMMODITIES: 'Global',
};

const EXTRA_TIMEZONE: Record<string, string> = {
  CN: 'Asia/Shanghai', TW: 'Asia/Taipei', HK: 'Asia/Hong_Kong', JP: 'Asia/Tokyo',
  KR: 'Asia/Seoul', SG: 'Asia/Singapore', MY: 'Asia/Kuala_Lumpur', AU: 'Australia/Sydney',
  UK: 'Europe/London', DE: 'Europe/Berlin', FR: 'Europe/Paris', NL: 'Europe/Amsterdam',
  CA: 'America/Toronto', BR: 'America/Sao_Paulo', MX: 'America/Mexico_City',
  SA: 'Asia/Riyadh', AE: 'Asia/Dubai', ZA: 'Africa/Johannesburg', EG: 'Africa/Cairo',
  NG: 'Africa/Lagos', RU: 'Europe/Moscow', TR: 'Europe/Istanbul', ID: 'Asia/Jakarta',
  TH: 'Asia/Bangkok', VN: 'Asia/Ho_Chi_Minh', FOREX: 'UTC', COMMODITIES: 'UTC',
};

/**
 * Resolve display metadata for a symbol+market. Cheap + pure, so it is safe to
 * call per render. Markets not explicitly mapped fall back to USD/US defaults.
 */
export function instrumentMeta(symbol: string, market: string, name?: string): InstrumentMeta {
  const m = toMarketId(market || 'US');
  const currencyCode = CURRENCY_CODE[m] || (m === 'CRYPTO' ? 'USD' : 'USD');
  // Prefer the native currency SYMBOL ($, ₹, £) and fall back to the code the
  // app already stores (PKR, SAR, AED…) when no familiar symbol exists.
  const currency = CURRENCY_SYMBOL[currencyCode] || MARKET_CURRENCY[m] || '$';
  const seed = SEED_BY_MARKET[m];
  const isCrypto = seed?.isCrypto ?? m === 'CRYPTO';
  const exchange = seed?.exchange ?? EXTRA_EXCHANGE[m] ?? m;
  const timezone = seed?.timezone ?? EXTRA_TIMEZONE[m] ?? 'UTC';

  return {
    symbol: symbol.toUpperCase(),
    market: m,
    name,
    currency,
    currencyCode,
    exchange,
    timezone,
    decimals: decimalsFor(currencyCode, isCrypto),
    marketName: MARKET_FULL_NAME[m] || m,
    isCrypto,
    isUsd: currencyCode === 'USD',
  };
}

/**
 * Default decimal precision for a market's currency. Sub-dollar instruments
 * (crypto) need more; most equities quote to 2.
 */
function decimalsFor(currencyCode: string, isCrypto: boolean): number {
  if (isCrypto) return 2;
  switch (currencyCode) {
    case 'JPY': case 'KRW': case 'IDR': case 'VND': return 0;
    default: return 2;
  }
}

/** True when the currency token is a glyph that binds tight to the number. */
function isSymbolGlyph(currency: string): boolean {
  return currency.length <= 2 && !/[A-Za-z]/.test(currency);
}

/** Format a price with the instrument's currency + precision.
 *  Symbols bind tight ("$245.32", "₹1,842.50"); currency codes get a space
 *  ("PKR 182.45", "SAR 27.10"). */
export function formatInstrumentPrice(meta: InstrumentMeta, value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return `${meta.currency} —`;
  const d = value < 1 && !Number.isInteger(value)
    ? Math.min(8, Math.max(meta.decimals, 4))
    : meta.decimals;
  const n = value.toLocaleString('en-US', { minimumFractionDigits: Math.min(d, meta.decimals), maximumFractionDigits: d });
  return `${meta.currency}${isSymbolGlyph(meta.currency) ? '' : ' '}${n}`;
}

/** Format an absolute change with sign + the instrument's precision. */
export function formatInstrumentChange(meta: InstrumentMeta, change: number | null | undefined): string {
  if (change == null || !Number.isFinite(change)) return '—';
  const n = Math.abs(change).toLocaleString('en-US', { minimumFractionDigits: meta.decimals, maximumFractionDigits: meta.decimals });
  const gap = isSymbolGlyph(meta.currency) ? '' : ' ';
  return `${change >= 0 ? '+' : '-'}${meta.currency}${gap}${n}`;
}

/** Format a percentage with sign and 2 decimals. */
export function formatPercent(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}

/** Compact volume / large-number formatting ("12.9M", "4.03K"). */
export function formatCompact(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toLocaleString('en-US', { maximumFractionDigits: 0 });
}

/** Tone class for a signed number. */
export function toneClass(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value) || value === 0) return 'text-muted-foreground';
  return value > 0 ? 'text-emerald-400' : 'text-rose-400';
}

// ── Market session status ────────────────────────────────────────────────────
// A best-effort open/closed/pre computation from the instrument's timezone and
// the market's local session hours. Crypto is always open. Unknown markets
// resolve to 'open' rather than falsely claiming closure.

export type SessionStatus = 'open' | 'pre' | 'after' | 'closed';

const SESSION_HOURS: Record<string, { open: number; close: number }> = {};
for (const seed of MARKET_SEEDS) SESSION_HOURS[seed.id] = { open: seed.openHour, close: seed.closeHour };

const DEFAULT_SESSION = { open: 9, close: 17 };

export function marketSession(meta: InstrumentMeta, now: Date = new Date()): SessionStatus {
  if (meta.isCrypto) return 'open';
  try {
    const fmt = new Intl.DateTimeFormat('en-US', {
      timeZone: meta.timezone, hour: 'numeric', minute: 'numeric', hour12: false, weekday: 'short',
    });
    const parts = fmt.formatToParts(now);
    const hour = Number(parts.find(p => p.type === 'hour')?.value ?? NaN);
    const wd = parts.find(p => p.type === 'weekday')?.value ?? '';
    const weekday = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(wd);
    if (!Number.isFinite(hour) || weekday < 0) return 'open';
    if (weekday === 0 || weekday === 6) return 'closed';
    const { open, close } = SESSION_HOURS[meta.market] ?? DEFAULT_SESSION;
    if (hour >= open && hour < close) return 'open';
    if (hour >= open - 2 && hour < open) return 'pre';
    if (hour >= close && hour < close + 3) return 'after';
    return 'closed';
  } catch {
    return 'open';
  }
}

export function sessionLabel(status: SessionStatus): string {
  switch (status) {
    case 'open': return 'MARKET OPEN';
    case 'pre': return 'PRE-MARKET';
    case 'after': return 'AFTER-HOURS';
    case 'closed': return 'MARKET CLOSED';
  }
}
