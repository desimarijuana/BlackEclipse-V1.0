// ── Yahoo Finance fundamentals provider ─────────────────────────────────────
// Secondary source / universal fallback. Runs the vendored yfinance bridge
// (`scripts/yfinance_fundamentals.py`), which returns up to 5 fiscal years of
// real statements plus a profile and ratios. No API key required.
//
// The bridge is optional infrastructure: when Python/yfinance are absent this
// provider reports unusable and the registry falls through to the next source.

import { existsSync } from 'fs';
import path from 'path';
import { findPython, runPythonBridge } from '@/lib/scraper/fetchers/python';
import { yahooSymbol } from '@/lib/scraper/fetchers/yfinance';
import type {
  EarningsEntry,
  FundamentalPeriod,
  Officer,
  ProviderFundamentals,
  FundamentalsProvider,
  OwnershipSnapshot,
  TimelineEntry,
  ValuationInputs,
} from '../types';

const BRIDGE_PATH = path.join(process.cwd(), 'scripts', 'yfinance_fundamentals.py');

const INFO_KEYS = [
  'longName', 'shortName', 'sector', 'industry', 'country', 'currency',
  'financialCurrency', 'website', 'longBusinessSummary', 'fullTimeEmployees',
  'marketCap', 'enterpriseValue', 'currentPrice', 'previousClose', 'beta',
  'trailingPE', 'forwardPE', 'pegRatio', 'trailingPegRatio', 'priceToBook',
  'priceToSalesTrailing12Months', 'enterpriseToEbitda', 'enterpriseToRevenue',
  'trailingEps', 'forwardEps', 'epsTrailingTwelveMonths', 'epsForward',
  'dividendRate', 'dividendYield', 'trailingAnnualDividendRate',
  'trailingAnnualDividendYield', 'payoutRatio', 'fiveYearAvgDividendYield',
  'totalCash', 'totalDebt', 'returnOnEquity', 'returnOnAssets',
  'grossMargins', 'operatingMargins', 'profitMargins', 'ebitdaMargins',
  'revenueGrowth', 'earningsGrowth', 'earningsQuarterlyGrowth',
  'currentRatio', 'quickRatio', 'debtToEquity', 'bookValue',
  'revenuePerShare', 'freeCashflow', 'operatingCashflow', 'totalRevenue',
  'grossProfits', 'ebitda', 'netIncomeToCommon',
  'heldPercentInstitutions', 'heldPercentInsiders', 'sharesOutstanding',
  'floatShares', 'sharesShort', 'shortPercentOfFloat', 'shortRatio',
  'recommendationKey', 'recommendationMean', 'numberOfAnalystOpinions',
  'targetHighPrice', 'targetLowPrice', 'targetMeanPrice', 'targetMedianPrice',
  'averageAnalystRating', 'mostRecentQuarter', 'lastFiscalYearEnd',
  'nextFiscalYearEnd', 'earningsTimestamp', 'earningsTimestampStart',
  'earningsTimestampEnd', 'isEarningsDateEstimate', 'exchange',
  'fullExchangeName', 'quoteType', 'allTimeHigh', 'allTimeLow',
] as const;

type InfoBag = Record<string, unknown>;

interface BridgeOutput {
  symbol?: string;
  currency?: string | null;
  info?: InfoBag;
  periods?: Array<Record<string, unknown>>;
  earnings?: { history?: EarningsEntry[] };
  officers?: Array<{ name?: string; title?: string; age?: number | null; yearBorn?: number | null; totalPay?: number | null }>;
  error?: string;
}

function n(info: InfoBag, key: string): number | null {
  const v = info[key];
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string') {
    const parsed = Number(v);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function s(info: InfoBag, ...keys: string[]): string | null {
  for (const key of keys) {
    const v = info[key];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return null;
}

/** Normalize the bridge's officer rows; drop any without a name AND title. */
function toOfficers(rows: BridgeOutput['officers']): Officer[] {
  if (!Array.isArray(rows)) return [];
  return rows
    .filter((o) => o && typeof o.name === 'string' && o.name.trim() && typeof o.title === 'string' && o.title.trim())
    .slice(0, 12)
    .map((o) => ({
      name: (o.name as string).trim(),
      title: (o.title as string).trim(),
      age: typeof o.age === 'number' ? o.age : null,
      yearBorn: typeof o.yearBorn === 'number' ? o.yearBorn : null,
      totalPay: typeof o.totalPay === 'number' ? o.totalPay : null,
      source: 'yahoo',
    }));
}

/** Convert a raw bridge period row (snake/camel-free names) into a period. */
function toPeriod(raw: Record<string, unknown>): FundamentalPeriod | null {
  const endDate = typeof raw.endDate === 'string' ? raw.endDate : null;
  if (!endDate) return null;
  const num = (key: string): number | null => {
    const v = raw[key];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };
  return {
    endDate,
    fiscalYear: null,
    revenue: num('revenue'),
    costOfRevenue: num('costOfRevenue'),
    grossProfit: num('grossProfit'),
    operatingIncome: num('operatingIncome'),
    ebitda: num('ebitda'),
    netIncome: num('netIncome'),
    eps: num('eps'),
    taxProvision: num('taxProvision'),
    pretaxIncome: num('pretaxIncome'),
    researchDevelopment: num('researchDevelopment'),
    interestExpense: num('interestExpense'),
    operatingCashFlow: num('operatingCashFlow'),
    capex: num('capex'),
    freeCashFlow: num('freeCashFlow'),
    dividendsPaid: num('dividendsPaid'),
    depreciation: num('depreciation'),
    totalAssets: num('totalAssets'),
    totalLiabilities: num('totalLiabilities'),
    totalEquity: num('totalEquity'),
    totalDebt: num('totalDebt'),
    netDebt: num('netDebt'),
    cash: num('cash'),
    currentAssets: num('currentAssets'),
    currentLiabilities: num('currentLiabilities'),
    inventory: num('inventory'),
    accountsReceivable: num('accountsReceivable'),
    sharesOutstanding: num('sharesOutstanding'),
    grossMargin: null,
    operatingMargin: null,
    netMargin: null,
    roe: null,
    roa: null,
    roic: null,
    debtToEquity: null,
    currentRatio: null,
    quickRatio: null,
  };
}

export function parseYahooFundamentals(data: BridgeOutput, symbol: string): ProviderFundamentals | null {
  const periods = (data.periods ?? [])
    .map(toPeriod)
    .filter((p): p is FundamentalPeriod => p !== null);
  const info = data.info ?? {};
  if (periods.length === 0 && Object.keys(info).length === 0) return null;

  const valuation: ValuationInputs = {
    trailingPE: n(info, 'trailingPE'),
    forwardPE: n(info, 'forwardPE'),
    peg: n(info, 'pegRatio') ?? n(info, 'trailingPegRatio'),
    priceToSales: n(info, 'priceToSalesTrailing12Months'),
    priceToBook: n(info, 'priceToBook'),
    evToEbitda: n(info, 'enterpriseToEbitda'),
    evToRevenue: n(info, 'enterpriseToRevenue'),
    fcfYield: null,
    // Yahoo returns `dividendYield` already in percent (0.32 = 0.32%) but the
    // annual variant as a fraction. Take the fraction form for consistency.
    dividendYield: n(info, 'trailingAnnualDividendYield'),
    dividendRate: n(info, 'dividendRate') ?? n(info, 'trailingAnnualDividendRate'),
    payoutRatio: n(info, 'payoutRatio'),
    trailingEps: n(info, 'epsTrailingTwelveMonths') ?? n(info, 'trailingEps'),
    forwardEps: n(info, 'epsForward') ?? n(info, 'forwardEps'),
  };

  const ownership: OwnershipSnapshot = {
    institutionalPercent: n(info, 'heldPercentInstitutions'),
    insiderPercent: n(info, 'heldPercentInsiders'),
    shortPercentOfFloat: n(info, 'shortPercentOfFloat'),
    sharesShort: n(info, 'sharesShort'),
    floatShares: n(info, 'floatShares'),
    source: 'yahoo',
  };

  const timeline: TimelineEntry[] = [];
  const lastFiscal = n(info, 'lastFiscalYearEnd');
  if (lastFiscal) {
    timeline.push({
      date: new Date(lastFiscal * 1000).toISOString().slice(0, 10),
      label: 'Fiscal year end (Yahoo)',
    });
  }

  return {
    provider: 'yahoo',
    symbol,
    currency: data.currency ?? s(info, 'financialCurrency', 'currency'),
    company: {
      name: s(info, 'longName', 'shortName'),
      sector: s(info, 'sector'),
      industry: s(info, 'industry'),
      country: s(info, 'country'),
      website: s(info, 'website'),
      description: s(info, 'longBusinessSummary'),
      employees: n(info, 'fullTimeEmployees'),
      exchange: s(info, 'fullExchangeName', 'exchange'),
      leadership: toOfficers(data.officers),
    },
    periods,
    quote: {
      price: n(info, 'currentPrice'),
      previousClose: n(info, 'previousClose'),
      marketCap: n(info, 'marketCap'),
      enterpriseValue: n(info, 'enterpriseValue'),
      sharesOutstanding: n(info, 'sharesOutstanding'),
      beta: n(info, 'beta'),
      source: 'yahoo',
    },
    valuation,
    earnings: { history: data.earnings?.history ?? [], estimates: [] },
    ownership,
    timeline,
    retrievedAt: new Date().toISOString(),
  };
}

let availability: { value: boolean; at: number } | null = null;
const AVAILABILITY_TTL_MS = 5 * 60 * 1000;

async function yahooAvailable(): Promise<boolean> {
  if (availability && Date.now() - availability.at < AVAILABILITY_TTL_MS) return availability.value;
  let ok = false;
  if (existsSync(BRIDGE_PATH)) {
    ok = (await findPython('yfinance')) !== null;
  }
  availability = { value: ok, at: Date.now() };
  return ok;
}

/** Test seam. */
export function __resetYahooAvailability(): void {
  availability = null;
}

export const yahooFundamentalsProvider: FundamentalsProvider = {
  id: 'yahoo',
  label: 'Yahoo Finance',

  isConfigured: yahooAvailable,
  // Yahoo covers every market the app charts; SEC only covers US issuers.
  supports: () => true,

  async fetch(symbol: string, market: string): Promise<ProviderFundamentals | null> {
    if (!existsSync(BRIDGE_PATH) || !(await yahooAvailable())) return null;
    const ticker = yahooSymbol(symbol.trim().toUpperCase(), market);
    try {
      const { stdout } = await runPythonBridge(BRIDGE_PATH, [ticker], {
        timeout: 90_000,
        maxBuffer: 16 * 1024 * 1024,
        mod: 'yfinance',
      });
      const text = stdout.trim();
      const start = text.indexOf('{');
      const parsed = JSON.parse(start >= 0 ? text.slice(start) : text) as BridgeOutput;
      if (parsed.error) return null;
      return parseYahooFundamentals(parsed, symbol.toUpperCase());
    } catch {
      return null;
    }
  },
};

export { INFO_KEYS };
