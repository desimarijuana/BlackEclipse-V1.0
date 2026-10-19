// ── SEC EDGAR fundamentals provider ─────────────────────────────────────────
// Preferred authoritative source for US issuers: XBRL company facts straight
// from the filings. Keyless — the SEC only asks for a descriptive User-Agent.
//
// Flow:
//   1. ticker → CIK via the cached company_tickers.json map (7-day JDDS cache),
//   2. one companyfacts.json request per symbol,
//   3. annual (10-K / FY) values for the ~20 us-gaap tags the Eclipse schema
//      needs, de-duplicated by period end date.
//
// Non-GAAP figures (EBITDA) are explicitly DERIVED (operating income +
// depreciation) because the SEC does not tag them. Everything else is a
// filed value; a missing tag stays null rather than being approximated.

import { prisma } from '@/lib/db';
import { safeGet } from '@/lib/connectors/security';
import type {
  FundamentalPeriod,
  FundamentalsProvider,
  ProviderFundamentals,
  TimelineEntry,
} from '../types';

// SEC's fair-access policy requires a declared User-Agent with a contact email.
// Verified: an email-shaped contact gets 200 where a URL-only UA gets 403.
// Exported so every SEC route (this provider, the filing-list capability)
// declares the SAME contact — one UA, not two that can drift.
export const SEC_USER_AGENT = 'BlackEclipse/1.0 (open-source financial research; contact@blackeclipse.local)';
const TICKERS_URL = 'https://www.sec.gov/files/company_tickers.json';
const FACTS_URL = (cik: number) =>
  `https://data.sec.gov/api/xbrl/companyfacts/CIK${String(cik).padStart(10, '0')}.json`;

const CIK_CACHE_KEY = 'sec_ticker_cik_v1';
const CIK_TTL_MS = 7 * 24 * 60 * 60 * 1000;

// ── Ticker → CIK map (cached in JDDS) ───────────────────────────────────────

let memoryMap: { map: Map<string, number>; at: number } | null = null;

async function loadCikMap(): Promise<Map<string, number>> {
  if (memoryMap && Date.now() - memoryMap.at < CIK_TTL_MS) return memoryMap.map;

  const cached = await prisma.systemConfig
    .findUnique({ where: { key: CIK_CACHE_KEY } })
    .catch(() => null);
  if (cached?.value) {
    try {
      const parsed = JSON.parse(cached.value) as { at: number; map: Record<string, number> };
      if (parsed.at && Date.now() - parsed.at < CIK_TTL_MS && parsed.map) {
        const map = new Map(Object.entries(parsed.map));
        memoryMap = { map, at: parsed.at };
        return map;
      }
    } catch {
      /* fall through to refetch */
    }
  }

  const res = await safeGet({
    url: TICKERS_URL,
    headers: { 'user-agent': SEC_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 8 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`SEC tickers HTTP ${res.status}`);
  const raw = JSON.parse(res.text) as Record<string, { cik_str: number; ticker: string }>;
  const map = new Map<string, number>();
  for (const entry of Object.values(raw)) {
    if (entry?.ticker) map.set(entry.ticker.toUpperCase(), entry.cik_str);
  }
  const at = Date.now();
  memoryMap = { map, at };
  await prisma.systemConfig
    .upsert({
      where: { key: CIK_CACHE_KEY },
      update: { value: JSON.stringify({ at, map: Object.fromEntries(map) }) },
      create: { key: CIK_CACHE_KEY, value: JSON.stringify({ at, map: Object.fromEntries(map) }) },
    })
    .catch(() => undefined);
  return map;
}

/** Test seam. */
export function __resetSecCikCache(): void {
  memoryMap = null;
}

/**
 * Resolve a US ticker to its SEC CIK via the cached company_tickers map.
 * Exposed for the filing-LIST bridge capability: the CIK map IS the US issuer
 * index, so that route needs no JDDS read and a ticker outside the map is
 * honestly unresolved (null) rather than guessed. A map READ failure throws —
 * the caller must tell "unreachable" apart from "no such ticker".
 */
export async function resolveSecCik(symbol: string): Promise<number | null> {
  const ticker = symbol.trim().toUpperCase();
  if (!ticker) return null;
  const map = await loadCikMap();
  return map.get(ticker) ?? null;
}

// ── XBRL fact extraction ────────────────────────────────────────────────────

interface XbrlUnitEntry {
  start?: string;
  end?: string;
  val: number;
  fy?: number;
  fp?: string;
  form?: string;
  filed?: string;
  frame?: string;
}
type CompanyFacts = {
  entityName?: string;
  facts?: Record<string, Record<string, { units?: Record<string, XbrlUnitEntry[]> }>>;
};

interface AnnualFact {
  end: string;
  val: number;
  form?: string;
  filed?: string;
  fy?: number;
  /** Index in the caller's tag-priority list; lower = more authoritative. */
  rank: number;
}

/**
 * Collect annual (10-K, fp=FY) values for a us-gaap tag. For duration concepts
 * (income/cash flow) we require `start`; for instant concepts (balance sheet)
 * there is no start — both are accepted because callers only ask for the tags
 * they expect. `instant` forces the no-start shape.
 */
function annualFacts(
  facts: CompanyFacts,
  tags: string[],
  opts: { instant?: boolean } = {}
): AnnualFact[] {
  const gaap = facts.facts?.['us-gaap'];
  if (!gaap) return [];
  const out: AnnualFact[] = [];
  tags.forEach((tag, rank) => {
    const units = gaap[tag]?.units;
    if (!units) return;
    const series = units.USD ?? units.shares ?? units['USD/shares'] ?? Object.values(units)[0];
    if (!series) return;
    for (const e of series) {
      if (!e?.end || !Number.isFinite(e.val)) continue;
      const form = (e.form ?? '').toUpperCase();
      const isAnnual = form.startsWith('10-K') || form.startsWith('20-F') || form.startsWith('40-F');
      if (!isAnnual) continue;
      if (!opts.instant) {
        if (!e.start) continue;
        // Duration concepts: a 10-K also carries quarterly windows. Keep only
        // ~annual spans (330–400 days) so a Q4 fact can never shadow the year.
        const days = (Date.parse(e.end) - Date.parse(e.start)) / 86_400_000;
        if (!(days >= 330 && days <= 400)) continue;
      }
      out.push({ end: e.end, val: e.val, form: e.form, filed: e.filed, fy: e.fy, rank });
    }
  });
  return out;
}

/**
 * Reduce facts to one value per period end date.
 *
 * Two things can differ across tags for the same end date, and both matter:
 *   1. tag authority — a preferred tag should win over a fallback tag;
 *   2. filing recency — a restatement should win over the original.
 *
 * A tag can also stop being reported while a fallback continues (e.g. NVIDIA
 * stopped tagging `RevenueFromContractWithCustomerExcludingAssessedTax` after
 * FY2022 and reports under `Revenues` since). So we keep the *union* of end
 * dates across tags and, per date, prefer the latest filing; only when two
 * facts share a filing date does tag rank break the tie.
 */
function latestByEnd(facts: AnnualFact[]): Map<string, AnnualFact> {
  const map = new Map<string, AnnualFact>();
  for (const f of facts) {
    const prev = map.get(f.end);
    if (!prev) {
      map.set(f.end, f);
      continue;
    }
    const filed = f.filed ?? '';
    const prevFiled = prev.filed ?? '';
    if (filed > prevFiled || (filed === prevFiled && f.rank < prev.rank)) {
      map.set(f.end, f);
    }
  }
  return map;
}

/** Values for a tag family, keyed by period end date (latest filing wins). */
function byEnd(facts: CompanyFacts, tags: string[], instant = false): Map<string, AnnualFact> {
  return latestByEnd(annualFacts(facts, tags, { instant }));
}

function pick(maps: Map<string, AnnualFact>[], end: string): AnnualFact | null {
  for (const map of maps) {
    const hit = map.get(end);
    if (hit) return hit;
  }
  return null;
}

const REVENUE = ['RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'Revenues', 'SalesRevenueNet'];
const COST = ['CostOfGoodsAndServicesSold', 'CostOfRevenue', 'CostOfGoodsSold'];
const GROSS = ['GrossProfit'];
const OP_INCOME = ['OperatingIncomeLoss'];
const NET_INCOME = ['NetIncomeLoss', 'ProfitLoss'];
const EPS = ['EarningsPerShareDiluted', 'EarningsPerShareBasic'];
const OCF = ['NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations'];
const CAPEX = ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets'];
const DIVIDENDS = ['PaymentsOfDividendsCommonStock', 'PaymentsOfDividends'];
const DEPR = ['DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet', 'Depreciation'];

const ASSETS = ['Assets'];
const LIABILITIES = ['Liabilities'];
const EQUITY = ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'];
const CASH = ['CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'];
const CURRENT_ASSETS = ['AssetsCurrent'];
const CURRENT_LIAB = ['LiabilitiesCurrent'];
const INVENTORY = ['InventoryNet'];
const RECEIVABLES = ['AccountsReceivableNetCurrent', 'ReceivablesNetCurrent'];
const LT_DEBT = ['LongTermDebtNoncurrent', 'LongTermDebt'];
const ST_DEBT = ['LongTermDebtCurrent', 'ShortTermBorrowings', 'DebtCurrent'];

function num(map: Map<string, AnnualFact> | null, end: string): number | null {
  if (!map) return null;
  const hit = map.get(end);
  return hit && Number.isFinite(hit.val) ? hit.val : null;
}

export function parseSecCompanyFacts(facts: CompanyFacts, symbol: string): ProviderFundamentals | null {
  const entityName = facts.entityName ?? null;
  const revenueMap = byEnd(facts, REVENUE);
  const grossMap = byEnd(facts, GROSS);
  const opMap = byEnd(facts, OP_INCOME);
  const netMap = byEnd(facts, NET_INCOME);
  const assetMap = byEnd(facts, ASSETS, true);
  if (revenueMap.size === 0 && netMap.size === 0) return null;

  const costMap = byEnd(facts, COST);
  const epsMap = byEnd(facts, EPS);
  const ocfMap = byEnd(facts, OCF);
  const capexMap = byEnd(facts, CAPEX);
  const divMap = byEnd(facts, DIVIDENDS);
  const deprMap = byEnd(facts, DEPR);
  const liabMap = byEnd(facts, LIABILITIES, true);
  const equityMap = byEnd(facts, EQUITY, true);
  const cashMap = byEnd(facts, CASH, true);
  const caMap = byEnd(facts, CURRENT_ASSETS, true);
  const clMap = byEnd(facts, CURRENT_LIAB, true);
  const invMap = byEnd(facts, INVENTORY, true);
  const arMap = byEnd(facts, RECEIVABLES, true);
  const ltdMap = byEnd(facts, LT_DEBT, true);
  const stdMap = byEnd(facts, ST_DEBT, true);

  // The union of every end date we have a statement value for.
  const ends = new Set<string>();
  for (const m of [revenueMap, grossMap, opMap, netMap, assetMap, ocfMap]) {
    for (const k of m.keys()) ends.add(k);
  }
  // Keep annual-ish periods only and the most recent ~8.
  const sorted = [...ends].sort().slice(-8);

  const periods: FundamentalPeriod[] = [];
  const filings: Array<{ end: string; form?: string; filed?: string }> = [];
  for (const end of sorted) {
    const revenue = num(revenueMap, end);
    const grossProfit = grossMap.get(end)?.val ?? null;
    const cost = costMap.get(end)?.val ?? (revenue !== null && grossProfit !== null ? revenue - grossProfit : null);
    const operatingIncome = num(opMap, end);
    const depreciation = num(deprMap, end);
    const ebitda = operatingIncome !== null ? operatingIncome + (depreciation ?? 0) : null;
    const cash = num(cashMap, end);
    const ltd = num(ltdMap, end) ?? 0;
    const std = num(stdMap, end) ?? 0;
    const totalDebt = ltd + std > 0 ? ltd + std : null;
    const netDebt = totalDebt !== null && cash !== null ? totalDebt - cash : null;
    const filedFact =
      pick([revenueMap, netMap, assetMap], end) ?? null;
    if (filedFact?.form) filings.push({ end, form: filedFact.form, filed: filedFact.filed });

    periods.push({
      endDate: end,
      // The issuer's fiscal-year LABEL is not assumed: SEC XBRL `fy` is the
      // filing context (it ran an off-by-one in fixtures), and a fiscal year does
      // not always equal the calendar year. `endDate` is preserved exactly; the
      // research layer matches an annual leg against the period end it falls in.
      fiscalYear: null,
      form: filedFact?.form,
      filed: filedFact?.filed,
      revenue,
      costOfRevenue: cost,
      grossProfit,
      operatingIncome,
      ebitda,
      netIncome: num(netMap, end),
      eps: num(epsMap, end),
      taxProvision: null,
      pretaxIncome: null,
      researchDevelopment: null,
      interestExpense: null,
      operatingCashFlow: num(ocfMap, end),
      capex: num(capexMap, end),
      freeCashFlow:
        num(ocfMap, end) !== null
          ? (num(ocfMap, end) as number) + (num(capexMap, end) ?? 0)
          : null,
      dividendsPaid: divMap.get(end)?.val ?? null,
      depreciation,
      totalAssets: num(assetMap, end),
      totalLiabilities: num(liabMap, end),
      totalEquity: num(equityMap, end),
      totalDebt,
      netDebt,
      cash,
      currentAssets: num(caMap, end),
      currentLiabilities: num(clMap, end),
      inventory: num(invMap, end),
      accountsReceivable: num(arMap, end),
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
    });
  }
  if (periods.length === 0) return null;

  const latestEnd = sorted[sorted.length - 1];
  const latestFiling = filings.find((f) => f.end === latestEnd);
  const timeline: TimelineEntry[] = latestFiling
    ? [
        {
          date: latestFiling.filed ?? latestEnd,
          label: `${latestFiling.form ?? '10-K'} filed for FY ending ${latestEnd}`,
          detail: 'SEC EDGAR filing',
          form: latestFiling.form,
          url: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${symbol}&type=10-K&dateb=&owner=include&count=10`,
        },
      ]
    : [];

  return {
    provider: 'sec-edgar',
    symbol,
    currency: 'USD',
    company: { name: entityName, country: 'United States' },
    periods,
    quote: null,
    valuation: null,
    earnings: { history: [], estimates: [] },
    ownership: null,
    timeline,
    retrievedAt: new Date().toISOString(),
  };
}

/**
 * Directly fetch and parse SEC company-facts for one US issuer, exposed for the
 * research bridge. Returns the same `ProviderFundamentals` the fundamentals page
 * uses, or null when the issuer is unsupported/unknown/unreachable. No second
 * SEC implementation: this is the one adapter, reused.
 */
export async function fetchSecCompanyFacts(
  symbol: string,
  market: string
): Promise<ProviderFundamentals | null> {
  if (!secFundamentalsProvider.supports(symbol, market)) return null;
  return secFundamentalsProvider.fetch(symbol, market);
}

let availability: { value: boolean; at: number } | null = null;
const AVAILABILITY_TTL_MS = 30 * 60 * 1000;

/** Whether SEC EDGAR is reachable right now (cached briefly). Exported for the
 * capability matrix so it reports SEC availability truthfully rather than
 * assuming it. */
export async function secAvailable(): Promise<boolean> {
  if (availability && Date.now() - availability.at < AVAILABILITY_TTL_MS) return availability.value;
  try {
    await loadCikMap();
    availability = { value: true, at: Date.now() };
  } catch {
    availability = { value: false, at: Date.now() };
  }
  return availability.value;
}

export const secFundamentalsProvider: FundamentalsProvider = {
  id: 'sec-edgar',
  label: 'SEC EDGAR',

  isConfigured: secAvailable,
  // SEC covers US-listed issuers only (no suffix).
  supports: (symbol, market) => market === 'US' && /^[A-Z][A-Z0-9.\-]{0,9}$/.test(symbol.toUpperCase()),

  async fetch(symbol: string, market: string): Promise<ProviderFundamentals | null> {
    if (!this.supports(symbol, market)) return null;
    if (!(await secAvailable())) return null;
    let cik: number | undefined;
    try {
      const map = await loadCikMap();
      cik = map.get(symbol.toUpperCase());
    } catch {
      return null;
    }
    if (!cik) return null;
    try {
      const res = await safeGet({
        url: FACTS_URL(cik),
        headers: { 'user-agent': SEC_USER_AGENT },
        timeoutMs: 10_000,
        maxBytes: 25 * 1024 * 1024,
      });
      if (res.status === 404) return null;
      if (res.status < 200 || res.status >= 300) return null;
      const facts = JSON.parse(res.text) as CompanyFacts;
      return parseSecCompanyFacts(facts, symbol.toUpperCase());
    } catch {
      return null;
    }
  },
};
