// ── PSX (Pakistan Stock Exchange) financials extractor ───────────────────────
// The PSX data portal embeds a company's annual + quarterly key financials as a
// plain HTML table on `https://dps.psx.com.pk/company/<SYMBOL>`:
//
//   Financials — "All numbers in thousands (000's) except EPS"
//   Annual:    Sales | Profit after Taxation | EPS      (columns = fiscal years)
//
// This is an OFFICIAL exchange source with no key. We parse it deterministically
// (cheerio) into real periods — never a model, never fabricated. Values are in
// thousands, so Sales / Profit are multiplied by 1,000; EPS is per share.
//
// This is the first of the per-market "official filings" adapters (P1). Adding a
// market = one file + a registration line.

import * as cheerio from 'cheerio';
import type { FundamentalPeriod } from '../types';

const PSX_COMPANY = 'https://dps.psx.com.pk/company/';
const HEADERS = {
  'User-Agent':
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
  Accept: 'text/html,application/xhtml+xml',
  'X-Requested-With': 'XMLHttpRequest',
};

/** One fiscal year of the three reported PSX lines. Values already in base PKR. */
export interface PsxYear {
  fiscalYear: number;
  revenue: number | null;
  netIncome: number | null;
  eps: number | null;
}

function toNum(raw: string | undefined): number | null {
  if (!raw) return null;
  const cleaned = raw.replace(/<[^>]+>/g, '').replace(/[,\s]/g, '').trim();
  if (!cleaned || cleaned === '-' || cleaned === '—') return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

/** Thousands → base units (PSX states "in thousands except EPS"). */
function thousands(v: number | null): number | null {
  return v == null ? null : v * 1000;
}

/**
 * Parse the annual financials table from a PSX company page. Exported for tests
 * (the HTML shape is the fragile part). Returns oldest-last? No — the page lists
 * newest first; we return them sorted oldest→newest to match the schema.
 */
export function parsePsxFinancials(html: string): PsxYear[] {
  if (!html) return [];
  const $ = cheerio.load(html);
  const annual = $('#financials [data-name="Annual"] table').first();
  if (annual.length === 0) return [];

  const years = annual
    .find('thead th')
    .map((_, th) => $(th).text().trim())
    .get()
    .filter((t) => /^\d{4}$/.test(t));
  if (years.length === 0) return [];

  const rows: Record<string, string[]> = {};
  annual.find('tbody tr').each((_, tr) => {
    const cells = $(tr).find('td').map((__, td) => $(td).text().trim()).get();
    if (cells.length >= 2) rows[cells[0].toLowerCase()] = cells.slice(1);
  });

  const sales = rows['sales'] ?? [];
  const profit = rows['profit after taxation'] ?? rows['profit after tax'] ?? rows['net profit'] ?? [];
  const eps = rows['eps'] ?? rows['earnings per share'] ?? [];

  const out: PsxYear[] = years.map((y, i) => ({
    fiscalYear: Number(y),
    revenue: thousands(toNum(sales[i])),
    netIncome: thousands(toNum(profit[i])),
    eps: toNum(eps[i]),
  }));
  return out.sort((a, b) => a.fiscalYear - b.fiscalYear);
}

/** Fetch and parse a PSX company's reported financials. Returns [] on any miss. */
export async function fetchPsxFinancials(symbol: string): Promise<PsxYear[]> {
  const ticker = symbol.trim().toUpperCase().replace(/\.PSX$/, '');
  if (!ticker) return [];
  try {
    const res = await fetch(`${PSX_COMPANY}${encodeURIComponent(ticker)}`, {
      headers: HEADERS,
      signal: AbortSignal.timeout(20000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    return parsePsxFinancials(await res.text());
  } catch {
    return [];
  }
}

/** Map PSX years into the Eclipse provider period shape. PK fiscal year ends
 *  June 30; we key the period by fiscal year end so it is comparable. */
export function psxYearsToPeriods(years: PsxYear[]): FundamentalPeriod[] {
  return years.map((y) => ({
    endDate: `${y.fiscalYear}-06-30`,
    fiscalYear: y.fiscalYear,
    revenue: y.revenue,
    costOfRevenue: null,
    grossProfit: null,
    operatingIncome: null,
    ebitda: null,
    netIncome: y.netIncome,
    eps: y.eps,
    taxProvision: null,
    pretaxIncome: null,
    researchDevelopment: null,
    interestExpense: null,
    operatingCashFlow: null,
    capex: null,
    freeCashFlow: null,
    dividendsPaid: null,
    depreciation: null,
    totalAssets: null,
    totalLiabilities: null,
    totalEquity: null,
    totalDebt: null,
    netDebt: null,
    cash: null,
    currentAssets: null,
    currentLiabilities: null,
    inventory: null,
    accountsReceivable: null,
    sharesOutstanding: null,
    grossMargin: null,
    operatingMargin: null,
    netMargin: null,
    roe: null,
    roa: null,
    roic: null,
    debtToEquity: null,
    currentRatio: null,
    quickRatio: null,
  }));
}
