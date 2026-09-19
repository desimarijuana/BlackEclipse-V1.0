// ── Financial Modeling Prep fundamentals provider (optional) ────────────────
// Normalized fundamentals + estimates, enabled only when the operator adds an
// FMP API key in Settings › API Keys (or FINANCIALMODELINGPREP_API_KEY env).
// This is the first pluggable "secondary normalized provider"; Alpha Vantage's
// OVERVIEW endpoint could be added the same way by appending another adapter.
//
// Without a key this provider is simply not configured and the registry falls
// through to SEC / Yahoo — zero-config installs are unaffected.

import { safeGet } from '@/lib/connectors/security';
import { resolveProviderKey } from '@/lib/provider-keys';
import type {
  FundamentalPeriod,
  FundamentalsProvider,
  ProviderFundamentals,
  TimelineEntry,
} from '../types';

export const FMP_KEY_ENV = 'FINANCIALMODELINGPREP_API_KEY';
const BASE = 'https://financialmodelingprep.com/api/v3';

interface FmpStatement {
  date?: string;
  calendarYear?: string;
  revenue?: number;
  costOfRevenue?: number;
  grossProfit?: number;
  operatingIncome?: number;
  ebitda?: number;
  netIncome?: number;
  epsdiluted?: number;
  eps?: number;
  incomeTaxExpense?: number;
  incomeBeforeTax?: number;
  researchAndDevelopmentExpenses?: number;
  interestExpense?: number;
  operatingCashFlow?: number;
  capitalExpenditure?: number;
  freeCashFlow?: number;
  dividendsPaid?: number;
  depreciationAndAmortization?: number;
  totalAssets?: number;
  totalLiabilities?: number;
  totalStockholdersEquity?: number;
  totalDebt?: number;
  netDebt?: number;
  cashAndCashEquivalents?: number;
  totalCurrentAssets?: number;
  totalCurrentLiabilities?: number;
  inventory?: number;
  netReceivables?: number;
  weightedAverageShsOutDil?: number;
}

interface FmpQuote {
  price?: number;
  previousClose?: number;
  marketCap?: number;
  enterpriseValue?: number;
  sharesOutstanding?: number;
  beta?: number;
  pe?: number;
  eps?: number;
  dividend?: number;
  dividendYield?: number;
}

interface FmpProfile {
  companyName?: string;
  sector?: string;
  industry?: string;
  country?: string;
  website?: string;
  description?: string;
  fullTimeEmployees?: string;
  exchangeShortName?: string;
  currency?: string;
  isEtf?: boolean;
  isFund?: boolean;
}

interface FmpRatios {
  priceToEarningsRatioTTM?: number;
  priceToSalesRatioTTM?: number;
  priceToBookRatioTTM?: number;
  enterpriseValueMultipleTTM?: number;
  dividendPayoutRatioTTM?: number;
}

interface FmpEstimate {
  date?: string;
  estimatedEpsAvg?: number;
  epsAvg?: number;
}

async function getJson<T>(url: string): Promise<T | null> {
  try {
    const res = await safeGet({ url, timeoutMs: 12_000, maxBytes: 8 * 1024 * 1024 });
    if (res.status < 200 || res.status >= 300) return null;
    const parsed = JSON.parse(res.text) as unknown;
    if (parsed && typeof parsed === 'object' && 'Error Message' in parsed) return null;
    return parsed as T;
  } catch {
    return null;
  }
}

function pickPeriod(
  income: FmpStatement | undefined,
  cashflow: FmpStatement | undefined,
  balance: FmpStatement | undefined
): FundamentalPeriod | null {
  const endDate = income?.date ?? balance?.date ?? cashflow?.date;
  if (!endDate) return null;
  const ocf = cashflow?.operatingCashFlow ?? null;
  const capex = cashflow?.capitalExpenditure ?? null;
  return {
    endDate,
    fiscalYear: income?.calendarYear ? Number(income.calendarYear) : null,
    revenue: income?.revenue ?? null,
    costOfRevenue: income?.costOfRevenue ?? null,
    grossProfit: income?.grossProfit ?? null,
    operatingIncome: income?.operatingIncome ?? null,
    ebitda: income?.ebitda ?? null,
    netIncome: income?.netIncome ?? null,
    eps: income?.epsdiluted ?? income?.eps ?? null,
    taxProvision: income?.incomeTaxExpense ?? null,
    pretaxIncome: income?.incomeBeforeTax ?? null,
    researchDevelopment: income?.researchAndDevelopmentExpenses ?? null,
    interestExpense: income?.interestExpense ?? null,
    operatingCashFlow: ocf,
    capex,
    freeCashFlow: cashflow?.freeCashFlow ?? (ocf !== null && capex !== null ? ocf + capex : null),
    dividendsPaid: cashflow?.dividendsPaid ?? null,
    depreciation: cashflow?.depreciationAndAmortization ?? null,
    totalAssets: balance?.totalAssets ?? null,
    totalLiabilities: balance?.totalLiabilities ?? null,
    totalEquity: balance?.totalStockholdersEquity ?? null,
    totalDebt: balance?.totalDebt ?? null,
    netDebt: balance?.netDebt ?? null,
    cash: balance?.cashAndCashEquivalents ?? null,
    currentAssets: balance?.totalCurrentAssets ?? null,
    currentLiabilities: balance?.totalCurrentLiabilities ?? null,
    inventory: balance?.inventory ?? null,
    accountsReceivable: balance?.netReceivables ?? null,
    sharesOutstanding: balance?.weightedAverageShsOutDil ?? null,
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

export function parseFmpFundamentals(
  symbol: string,
  income: FmpStatement[] | null,
  cashflow: FmpStatement[] | null,
  balance: FmpStatement[] | null,
  quote: FmpQuote[] | null,
  profile: FmpProfile[] | null,
  ratios: FmpRatios[] | null,
  estimates: FmpEstimate[] | null
): ProviderFundamentals | null {
  const inc = income ?? [];
  if (inc.length === 0) return null;
  const cfByDate = new Map((cashflow ?? []).map((r) => [r.date ?? '', r]));
  const bsByDate = new Map((balance ?? []).map((r) => [r.date ?? '', r]));
  const periods = inc
    .map((row) => pickPeriod(row, cfByDate.get(row.date ?? ''), bsByDate.get(row.date ?? '')))
    .filter((p): p is FundamentalPeriod => p !== null)
    .sort((a, b) => a.endDate.localeCompare(b.endDate));
  if (periods.length === 0) return null;

  const q = quote?.[0];
  const p = profile?.[0];
  const r = ratios?.[0];
  const timeline: TimelineEntry[] = [
    { date: periods[periods.length - 1].endDate, label: 'Latest annual statements (FMP)' },
  ];

  return {
    provider: 'financialmodelingprep',
    symbol,
    currency: p?.currency ?? 'USD',
    company: {
      name: p?.companyName ?? null,
      sector: p?.sector ?? null,
      industry: p?.industry ?? null,
      country: p?.country ?? null,
      website: p?.website ?? null,
      description: p?.description ?? null,
      employees: p?.fullTimeEmployees ? Number(p.fullTimeEmployees) : null,
      exchange: p?.exchangeShortName ?? null,
    },
    periods,
    quote: q
      ? {
          price: q.price ?? null,
          previousClose: q.previousClose ?? null,
          marketCap: q.marketCap ?? null,
          enterpriseValue: q.enterpriseValue ?? null,
          sharesOutstanding: q.sharesOutstanding ?? null,
          beta: q.beta ?? null,
          source: 'financialmodelingprep',
        }
      : null,
    valuation: {
      trailingPE: q?.pe ?? r?.priceToEarningsRatioTTM ?? null,
      forwardPE: null,
      peg: null,
      priceToSales: r?.priceToSalesRatioTTM ?? null,
      priceToBook: r?.priceToBookRatioTTM ?? null,
      evToEbitda: r?.enterpriseValueMultipleTTM ?? null,
      evToRevenue: null,
      fcfYield: null,
      dividendYield: q?.dividendYield ?? null,
      dividendRate: q?.dividend ?? null,
      payoutRatio: r?.dividendPayoutRatioTTM ?? null,
      trailingEps: q?.eps ?? null,
      forwardEps: estimates?.[0]?.estimatedEpsAvg ?? estimates?.[0]?.epsAvg ?? null,
    },
    earnings: {
      history: [],
      estimates: (estimates ?? []).map((e) => ({
        date: e.date ?? '',
        actual: null,
        estimate: e.estimatedEpsAvg ?? e.epsAvg ?? null,
      })),
    },
    ownership: null,
    timeline,
    retrievedAt: new Date().toISOString(),
  };
}

async function apiKey(): Promise<string | null> {
  return resolveProviderKey(FMP_KEY_ENV);
}

export const fmpFundamentalsProvider: FundamentalsProvider = {
  id: 'financialmodelingprep',
  label: 'Financial Modeling Prep',

  async isConfigured() {
    return (await apiKey()) !== null;
  },
  supports: () => true,

  async fetch(symbol: string, _market: string): Promise<ProviderFundamentals | null> {
    const key = await apiKey();
    if (!key) return null;
    const sym = symbol.trim().toUpperCase();
    const tag = `symbol=${encodeURIComponent(sym)}&limit=6&apikey=${encodeURIComponent(key)}`;
    const [income, cashflow, balance, quote, profile, ratios, estimates] = await Promise.all([
      getJson<FmpStatement[]>(`${BASE}/income-statement/${encodeURIComponent(sym)}?period=annual&${tag}`),
      getJson<FmpStatement[]>(`${BASE}/cash-flow-statement/${encodeURIComponent(sym)}?period=annual&${tag}`),
      getJson<FmpStatement[]>(`${BASE}/balance-sheet-statement/${encodeURIComponent(sym)}?period=annual&${tag}`),
      getJson<FmpQuote[]>(`${BASE}/quote/${encodeURIComponent(sym)}?apikey=${encodeURIComponent(key)}`),
      getJson<FmpProfile[]>(`${BASE}/profile/${encodeURIComponent(sym)}?apikey=${encodeURIComponent(key)}`),
      getJson<FmpRatios[]>(`${BASE}/ratios-ttm/${encodeURIComponent(sym)}?apikey=${encodeURIComponent(key)}`),
      getJson<FmpEstimate[]>(`${BASE}/analyst-estimates/${encodeURIComponent(sym)}?apikey=${encodeURIComponent(key)}`),
    ]);
    if (!income || !Array.isArray(income)) return null;
    return parseFmpFundamentals(sym, income, cashflow, balance, quote, profile, ratios, estimates);
  },
};


