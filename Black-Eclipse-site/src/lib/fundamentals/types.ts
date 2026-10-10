// ── Eclipse Fundamentals schema ─────────────────────────────────────────────
// The single canonical shape every fundamentals provider normalizes into. The
// UI depends ONLY on these types — never on Yahoo/SEC/FMP field names. Provider
// adapters live in `./providers`, the normalizer in `./normalize`, derived
// metrics + risk synthesis in `./compute`.

/** Providers the fundamentals layer can pull from, in precedence order. */
export type FundamentalProviderId = 'sec-edgar' | 'financialmodelingprep' | 'yahoo' | 'eclipse-filings';

export const PROVIDER_LABELS: Record<FundamentalProviderId, string> = {
  'sec-edgar': 'SEC EDGAR',
  financialmodelingprep: 'Financial Modeling Prep',
  yahoo: 'Yahoo Finance',
  'eclipse-filings': 'Eclipse Filings (exchange)',
};

/** Where a single displayed value came from. `derived` = computed from raw. */
export type MetricSource = FundamentalProviderId | 'derived';

export type MetricUnit = 'currency' | 'percent' | 'ratio' | 'shares' | 'number';

/** `higher` means a rising value is good (margins, growth); `lower` the reverse. */
export type MetricPolarity = 'higher' | 'lower' | 'neutral';

export interface MetricReference {
  /** Human label, e.g. "10-K FY2025". */
  label: string;
  /** Traceable source URL (SEC filing index, provider page). */
  url?: string;
  form?: string;
  filed?: string;
}

/**
 * One investor-facing value. Every metric on the page carries value, period,
 * YoY change, source and last-updated so a number can never be read as an
 * isolated, timeless fact.
 */
export interface FundamentalMetric {
  key: string;
  label: string;
  value: number | null;
  unit: MetricUnit;
  /** Period the value describes, e.g. "FY2025" or "2025-09-30". */
  period: string | null;
  /** Relative change vs the prior comparable period (0.12 = +12%). */
  yoy: number | null;
  source: MetricSource;
  updatedAt: string | null;
  polarity: MetricPolarity;
  ref?: MetricReference;
}

/** One fiscal year of statements, all in the reporting currency. */
export interface FundamentalPeriod {
  endDate: string;
  fiscalYear: number | null;
  form?: string;
  filed?: string;
  // Income statement
  revenue: number | null;
  costOfRevenue: number | null;
  grossProfit: number | null;
  operatingIncome: number | null;
  ebitda: number | null;
  netIncome: number | null;
  eps: number | null;
  taxProvision: number | null;
  pretaxIncome: number | null;
  researchDevelopment: number | null;
  interestExpense: number | null;
  // Cash flow
  operatingCashFlow: number | null;
  capex: number | null;
  freeCashFlow: number | null;
  dividendsPaid: number | null;
  depreciation: number | null;
  // Balance sheet
  totalAssets: number | null;
  totalLiabilities: number | null;
  totalEquity: number | null;
  totalDebt: number | null;
  netDebt: number | null;
  cash: number | null;
  currentAssets: number | null;
  currentLiabilities: number | null;
  inventory: number | null;
  accountsReceivable: number | null;
  sharesOutstanding: number | null;
  // Derived per-period ratios (computed in `compute.ts`)
  grossMargin: number | null;
  operatingMargin: number | null;
  netMargin: number | null;
  roe: number | null;
  roa: number | null;
  roic: number | null;
  debtToEquity: number | null;
  currentRatio: number | null;
  quickRatio: number | null;
}

export interface CompanyProfile {
  name: string | null;
  sector: string | null;
  industry: string | null;
  country: string | null;
  website: string | null;
  description: string | null;
  employees: number | null;
  exchange: string | null;
  /** Named executives when the provider discloses them (name + title). */
  leadership?: Officer[];
}

/** One disclosed executive. `source` records where the name came from so the UI
 *  never presents an old/first-seen officer as verified-current without context. */
export interface Officer {
  name: string;
  title: string;
  age?: number | null;
  yearBorn?: number | null;
  /** Total reported compensation for the last fiscal year, when disclosed. */
  totalPay?: number | null;
  source?: FundamentalProviderId;
}

/** Market-derived figures that complement the filings. */
export interface QuoteSnapshot {
  price: number | null;
  previousClose: number | null;
  marketCap: number | null;
  enterpriseValue: number | null;
  sharesOutstanding: number | null;
  beta: number | null;
  fiftyTwoWeekHigh: number | null;
  fiftyTwoWeekLow: number | null;
  source: MetricSource;
  updatedAt: string | null;
}

export interface EarningsEntry {
  date: string;
  actual: number | null;
  estimate: number | null;
}

/**
 * Neutral valuation inputs. Providers translate their own ratio field names
 * into this bag; anything omitted is derived from price/market-cap + the
 * statements by `compute.ts`. `dividendYield`/`payoutRatio` are fractions.
 */
export interface ValuationInputs {
  trailingPE: number | null;
  forwardPE: number | null;
  peg: number | null;
  priceToSales: number | null;
  priceToBook: number | null;
  evToEbitda: number | null;
  evToRevenue: number | null;
  fcfYield: number | null;
  dividendYield: number | null;
  dividendRate: number | null;
  payoutRatio: number | null;
  trailingEps: number | null;
  forwardEps: number | null;
}

export interface OwnershipSnapshot {
  institutionalPercent: number | null;
  insiderPercent: number | null;
  shortPercentOfFloat: number | null;
  sharesShort: number | null;
  floatShares: number | null;
  source: MetricSource;
}

/** Derived per-period growth series for the trend panels. */
export interface GrowthSeries {
  revenue: Array<{ period: string; value: number | null }>;
  eps: Array<{ period: string; value: number | null }>;
  freeCashFlow: Array<{ period: string; value: number | null }>;
}

/** A data-driven observation or risk synthesized from the actual statements. */
export type InsightTone = 'positive' | 'negative' | 'neutral' | 'warning';

export interface FundamentalInsight {
  id: string;
  tone: InsightTone;
  title: string;
  detail: string;
  /** Metric keys the insight is grounded in. */
  evidence: string[];
}

export interface TimelineEntry {
  date: string;
  label: string;
  detail?: string;
  form?: string;
  url?: string;
}

export type FundamentalsProvenance = 'LIVE' | 'CACHED' | 'HISTORICAL' | 'UNAVAILABLE';

export interface FundamentalsSnapshot {
  symbol: string;
  market: string;
  currency: string | null;
  company: CompanyProfile;
  /** Provider that supplied the statement periods. */
  primarySource: MetricSource;
  /** All providers that contributed (for the source line). */
  contributors: MetricSource[];
  provenance: FundamentalsProvenance;
  retrievedAt: string;
  fiscalYearEnd: string | null;
  periods: FundamentalPeriod[];
  growth: GrowthSeries;
  quote: QuoteSnapshot | null;
  metrics: FundamentalMetric[];
  earnings: { history: EarningsEntry[]; estimates: EarningsEntry[] };
  ownership: OwnershipSnapshot | null;
  insights: FundamentalInsight[];
  timeline: TimelineEntry[];
}

/** Per-provider raw output, before normalization into the Eclipse schema. */
export interface ProviderFundamentals {
  provider: FundamentalProviderId;
  symbol: string;
  currency: string | null;
  company: Partial<CompanyProfile>;
  periods: Omit<
    FundamentalPeriod,
    | 'fiscalYear'
    | 'grossMargin'
    | 'operatingMargin'
    | 'netMargin'
    | 'roe'
    | 'roa'
    | 'roic'
    | 'debtToEquity'
    | 'currentRatio'
    | 'quickRatio'
  >[];
  quote?: Partial<QuoteSnapshot> | null;
  valuation?: Partial<ValuationInputs> | null;
  earnings?: { history: EarningsEntry[]; estimates: EarningsEntry[] };
  ownership?: Partial<OwnershipSnapshot> | null;
  timeline?: TimelineEntry[];
  retrievedAt: string;
}

export interface FundamentalsProvider {
  readonly id: FundamentalProviderId;
  readonly label: string;
  /** Whether the provider is usable right now (key present, runtime available). */
  isConfigured(): Promise<boolean> | boolean;
  /** Whether this provider can serve the given symbol/market pair. */
  supports(symbol: string, market: string): boolean;
  /**
   * Fetch and normalize raw provider data. MUST return null (never invent data)
   * when the issuer is unknown or the source has no fundamentals.
   */
  fetch(symbol: string, market: string): Promise<ProviderFundamentals | null>;
}
