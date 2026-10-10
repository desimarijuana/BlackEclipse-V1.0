// ── Derived metrics, growth, valuation and data-driven risk synthesis ───────
// Everything here is computed from the normalized statements + quote + neutral
// valuation inputs. NOTHING is fabricated: a metric with no inputs is null and
// renders as UNAVAILABLE in the UI.

import { latestReportingPeriod } from './normalize';
import type { PeriodConflict } from './reconcile';
import type {
  CompanyProfile,
  EarningsEntry,
  FundamentalInsight,
  FundamentalMetric,
  FundamentalPeriod,
  FundamentalsSnapshot,
  GrowthSeries,
  MetricPolarity,
  MetricSource,
  OwnershipSnapshot,
  QuoteSnapshot,
  TimelineEntry,
  ValuationInputs,
} from './types';

/** Compound annual growth rate over `years`, or null when not computable. */
export function cagr(start: number | null, end: number | null, years: number): number | null {
  if (start === null || end === null || years <= 0) return null;
  if (start <= 0 || end < 0) return null;
  const r = Math.pow(end / start, 1 / years) - 1;
  return Number.isFinite(r) ? r : null;
}

/** Simple growth from one period to the next. */
function growth(prev: number | null, curr: number | null): number | null {
  if (prev === null || curr === null || prev === 0) return null;
  const g = (curr - prev) / Math.abs(prev);
  return Number.isFinite(g) ? g : null;
}

/**
 * Percent metrics are stored as FRACTIONS (0.152 = 15.2%) uniformly across the
 * schema — including growth, margins, returns, yields and payout. The UI owns
 * the ×100 formatting. Rounding guards the 0.30000000000000004 artifacts.
 */
function fraction(n: number | null): number | null {
  return n === null ? null : Math.round(n * 1e6) / 1e6;
}

/** Latest-vs-prior YoY across the period list for a chosen field. */
function latestYoY(periods: FundamentalPeriod[], field: keyof FundamentalPeriod): number | null {
  if (periods.length < 2) return null;
  const curr = periods[periods.length - 1];
  const prev = periods[periods.length - 2];
  return growth(prev[field] as number | null, curr[field] as number | null);
}

function valueOf(p: FundamentalPeriod | null, field: keyof FundamentalPeriod): number | null {
  if (!p) return null;
  const v = p[field];
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}

// ── Growth series ────────────────────────────────────────────────────────────

export function buildGrowth(periods: FundamentalPeriod[]): GrowthSeries {
  const series = (field: keyof FundamentalPeriod) =>
    periods.map((p) => ({ period: p.endDate, value: valueOf(p, field) }));
  return {
    revenue: series('revenue'),
    eps: series('eps'),
    freeCashFlow: series('freeCashFlow'),
  };
}

// ── Metrics assembly ─────────────────────────────────────────────────────────

interface MetricSpec {
  key: string;
  label: string;
  value: number | null;
  unit: FundamentalMetric['unit'];
  polarity: MetricPolarity;
  yoy?: number | null;
  source?: MetricSource;
}

function buildMetricsFromSpecs(
  specs: MetricSpec[],
  period: string | null,
  updatedAt: string | null,
  primary: MetricSource,
  ref: FundamentalMetric['ref']
): FundamentalMetric[] {
  return specs.map((s) => ({
    key: s.key,
    label: s.label,
    value: s.value,
    unit: s.unit,
    period,
    yoy: s.yoy ?? null,
    source: s.source ?? primary,
    updatedAt,
    polarity: s.polarity,
    ref,
  }));
}

export interface AssembleInputs {
  symbol: string;
  market: string;
  currency: string | null;
  company: CompanyProfile;
  periods: FundamentalPeriod[];
  growth: GrowthSeries;
  quote: QuoteSnapshot | null;
  valuation: ValuationInputs;
  /** Provider that supplied the valuation inputs (for honest source labels). */
  valuationSource: MetricSource;
  earnings: { history: EarningsEntry[]; estimates: EarningsEntry[] };
  ownership: OwnershipSnapshot | null;
  timeline: TimelineEntry[];
  primary: MetricSource;
  contributors: MetricSource[];
  provenance: FundamentalsSnapshot['provenance'];
  retrievedAt: string;
  fiscalYearEnd: string | null;
  /** Cross-source disagreements detected during reconciliation (P3). */
  conflicts?: PeriodConflict[];
}

export function assembleSnapshot(input: AssembleInputs): FundamentalsSnapshot {
  const { periods, quote, valuation, primary, valuationSource } = input;
  const latest = latestReportingPeriod(periods);
  // Use the latest period even if it has no revenue so its ratios still render.
  const period = latest?.endDate ?? null;
  const updatedAt = input.retrievedAt;

  const shares = quote?.sharesOutstanding ?? valueOf(latest, 'sharesOutstanding');
  const marketCap =
    quote?.marketCap ?? (quote?.price !== null && quote?.price !== undefined && shares ? quote.price * shares : null);
  const price = quote?.price ?? null;
  const eps = valuation.trailingEps ?? valueOf(latest, 'eps');
  const revenue = valueOf(latest, 'revenue');
  const ebitda = valueOf(latest, 'ebitda');
  const equity = valueOf(latest, 'totalEquity');
  const totalDebt = valueOf(latest, 'totalDebt');
  const cash = valueOf(latest, 'cash');
  const netDebt = valueOf(latest, 'netDebt') ?? (totalDebt !== null && cash !== null ? totalDebt - cash : null);
  const fcf = valueOf(latest, 'freeCashFlow');
  const enterpriseValue =
    quote?.enterpriseValue ??
    (marketCap !== null && netDebt !== null ? marketCap + netDebt : marketCap);

  // Prefer provider-reported multiples; otherwise derive honestly from inputs.
  const pe = valuation.trailingPE ?? (price !== null && eps ? price / eps : null);
  const forwardPE =
    valuation.forwardPE ??
    (price !== null && valuation.forwardEps ? price / valuation.forwardEps : null);
  const ps = valuation.priceToSales ?? (marketCap !== null && revenue ? marketCap / revenue : null);
  const pb = valuation.priceToBook ?? (marketCap !== null && equity ? marketCap / equity : null);
  const evEbitda = valuation.evToEbitda ?? (enterpriseValue !== null && ebitda ? enterpriseValue / ebitda : null);
  const evRevenue = valuation.evToRevenue ?? (enterpriseValue !== null && revenue ? enterpriseValue / revenue : null);
  const fcfYield = valuation.fcfYield ?? (marketCap !== null && fcf !== null ? fcf / marketCap : null);
  const peg =
    valuation.peg ??
    (pe !== null && latest ? derivePeg(pe, input.growth.eps) : null);
  const payout = valuation.payoutRatio ?? null;

  const rev3 = cagr(valueOf(periods[Math.max(0, periods.length - 4)], 'revenue'), revenue, 3);
  const rev5 = cagr(valueOf(periods[Math.max(0, periods.length - 6)], 'revenue'), revenue, 5);
  const eps3 = cagr(valueOf(periods[Math.max(0, periods.length - 4)], 'eps'), valueOf(latest, 'eps'), 3);
  const fcf3 = cagr(valueOf(periods[Math.max(0, periods.length - 4)], 'freeCashFlow'), fcf, 3);

  const specs: MetricSpec[] = [
    // Profitability
    { key: 'revenue', label: 'Revenue', value: revenue, unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'revenue') },
    { key: 'grossProfit', label: 'Gross Profit', value: valueOf(latest, 'grossProfit'), unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'grossProfit') },
    { key: 'operatingIncome', label: 'Operating Income', value: valueOf(latest, 'operatingIncome'), unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'operatingIncome') },
    { key: 'ebitda', label: 'EBITDA', value: ebitda, unit: 'currency', polarity: 'higher' },
    { key: 'netIncome', label: 'Net Income', value: valueOf(latest, 'netIncome'), unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'netIncome') },
    { key: 'eps', label: 'EPS (Diluted)', value: valueOf(latest, 'eps'), unit: 'number', polarity: 'higher', yoy: latestYoY(periods, 'eps') },
    // Cash flow
    { key: 'operatingCashFlow', label: 'Operating Cash Flow', value: valueOf(latest, 'operatingCashFlow'), unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'operatingCashFlow') },
    { key: 'capex', label: 'Capital Expenditure', value: valueOf(latest, 'capex'), unit: 'currency', polarity: 'lower' },
    { key: 'freeCashFlow', label: 'Free Cash Flow', value: fcf, unit: 'currency', polarity: 'higher', yoy: latestYoY(periods, 'freeCashFlow') },
    // Margins
    { key: 'grossMargin', label: 'Gross Margin', value: fraction(valueOf(latest, 'grossMargin')), unit: 'percent', polarity: 'higher' },
    { key: 'operatingMargin', label: 'Operating Margin', value: fraction(valueOf(latest, 'operatingMargin')), unit: 'percent', polarity: 'higher' },
    { key: 'netMargin', label: 'Net Margin', value: fraction(valueOf(latest, 'netMargin')), unit: 'percent', polarity: 'higher' },
    // Returns
    { key: 'roe', label: 'ROE', value: fraction(valueOf(latest, 'roe')), unit: 'percent', polarity: 'higher' },
    { key: 'roa', label: 'ROA', value: fraction(valueOf(latest, 'roa')), unit: 'percent', polarity: 'higher' },
    { key: 'roic', label: 'ROIC', value: fraction(valueOf(latest, 'roic')), unit: 'percent', polarity: 'higher' },
    // Balance sheet
    { key: 'debt', label: 'Total Debt', value: totalDebt, unit: 'currency', polarity: 'lower' },
    { key: 'cash', label: 'Cash & Equivalents', value: cash, unit: 'currency', polarity: 'higher' },
    { key: 'netDebt', label: 'Net Debt', value: netDebt, unit: 'currency', polarity: 'lower' },
    { key: 'debtToEquity', label: 'Debt / Equity', value: valueOf(latest, 'debtToEquity'), unit: 'ratio', polarity: 'lower' },
    { key: 'currentRatio', label: 'Current Ratio', value: valueOf(latest, 'currentRatio'), unit: 'ratio', polarity: 'higher' },
    { key: 'quickRatio', label: 'Quick Ratio', value: valueOf(latest, 'quickRatio'), unit: 'ratio', polarity: 'higher' },
    // Growth
    { key: 'revenueGrowth', label: 'Revenue Growth (YoY)', value: fraction(latestYoY(periods, 'revenue')), unit: 'percent', polarity: 'higher' },
    { key: 'epsGrowth', label: 'EPS Growth (YoY)', value: fraction(latestYoY(periods, 'eps')), unit: 'percent', polarity: 'higher' },
    { key: 'fcfGrowth', label: 'FCF Growth (YoY)', value: fraction(latestYoY(periods, 'freeCashFlow')), unit: 'percent', polarity: 'higher' },
    { key: 'revenueCagr3', label: 'Revenue CAGR (3Y)', value: fraction(rev3), unit: 'percent', polarity: 'higher' },
    { key: 'revenueCagr5', label: 'Revenue CAGR (5Y)', value: fraction(rev5), unit: 'percent', polarity: 'higher' },
    { key: 'epsCagr3', label: 'EPS CAGR (3Y)', value: fraction(eps3), unit: 'percent', polarity: 'higher' },
    { key: 'fcfCagr3', label: 'FCF CAGR (3Y)', value: fraction(fcf3), unit: 'percent', polarity: 'higher' },
    // Valuation
    { key: 'pe', label: 'P/E', value: pe, unit: 'ratio', polarity: 'lower', source: valuation.trailingPE !== null ? valuationSource : 'derived' },
    { key: 'forwardPE', label: 'Forward P/E', value: forwardPE, unit: 'ratio', polarity: 'lower', source: valuation.forwardPE !== null ? valuationSource : 'derived' },
    { key: 'peg', label: 'PEG', value: peg, unit: 'ratio', polarity: 'lower', source: valuation.peg !== null ? valuationSource : 'derived' },
    { key: 'ps', label: 'P/S', value: ps, unit: 'ratio', polarity: 'lower', source: valuation.priceToSales !== null ? valuationSource : 'derived' },
    { key: 'pb', label: 'P/B', value: pb, unit: 'ratio', polarity: 'lower', source: valuation.priceToBook !== null ? valuationSource : 'derived' },
    { key: 'evEbitda', label: 'EV / EBITDA', value: evEbitda, unit: 'ratio', polarity: 'lower', source: valuation.evToEbitda !== null ? valuationSource : 'derived' },
    { key: 'evRevenue', label: 'EV / Revenue', value: evRevenue, unit: 'ratio', polarity: 'lower', source: valuation.evToRevenue !== null ? valuationSource : 'derived' },
    { key: 'fcfYield', label: 'FCF Yield', value: fraction(fcfYield), unit: 'percent', polarity: 'higher', source: valuation.fcfYield !== null ? valuationSource : 'derived' },
    // Dividends
    { key: 'dividendRate', label: 'Dividend / Share', value: valuation.dividendRate, unit: 'currency', polarity: 'higher', source: valuation.dividendRate !== null ? valuationSource : 'derived' },
    { key: 'dividendYield', label: 'Dividend Yield', value: fraction(valuation.dividendYield), unit: 'percent', polarity: 'higher', source: valuation.dividendYield !== null ? valuationSource : 'derived' },
    { key: 'payoutRatio', label: 'Payout Ratio', value: fraction(payout), unit: 'percent', polarity: 'neutral', source: valuation.payoutRatio !== null ? valuationSource : 'derived' },
  ];

  const ref = input.timeline.find((t) => t.url) ?? undefined;
  const metrics = buildMetricsFromSpecs(
    specs,
    period,
    updatedAt,
    primary,
    ref ? { label: ref.label, url: ref.url, form: ref.form } : undefined
  );

  const insights = synthesizeInsights({
    periods,
    latest,
    metrics,
    growth: input.growth,
    netDebt,
    ebitda,
    fcf,
    marketCap,
    cash,
    totalDebt,
    equity,
    revenue,
    currency: input.currency,
    primary,
  });

  // Surface cross-source disagreements (never silently averaged).
  const conflictInsights: FundamentalInsight[] = (input.conflicts ?? []).slice(0, 4).map((c, i) => ({
    id: `cross-source-${i}`,
    tone: c.maxDeltaPct >= 10 ? 'warning' : 'neutral',
    title: `Cross-source disagreement — ${c.metric} (${c.endDate})`,
    detail: `${c.values.map((v) => `${v.provider} ${v.value.toLocaleString('en-US')}`).join(' · ')} — a ${c.maxDeltaPct.toFixed(1)}% difference. Shown, not averaged.`,
    evidence: [c.metric],
  }));
  const allInsights = [...conflictInsights, ...insights];

  return {
    symbol: input.symbol,
    market: input.market,
    currency: input.currency,
    company: input.company,
    primarySource: primary,
    contributors: input.contributors,
    provenance: input.provenance,
    retrievedAt: input.retrievedAt,
    fiscalYearEnd: input.fiscalYearEnd,
    periods,
    growth: input.growth,
    quote,
    metrics,
    earnings: input.earnings,
    ownership: input.ownership,
    insights: allInsights,
    timeline: input.timeline,
  };
}

/** PEG using the latest EPS growth; null when growth is non-positive. */
function derivePeg(pe: number, growthSeries: GrowthSeries['eps']): number | null {
  const values = growthSeries.map((p) => p.value).filter((v): v is number => v !== null);
  if (values.length < 2 || values[0] <= 0) return null;
  const last = values[values.length - 1];
  const prev = values[values.length - 2];
  if (prev <= 0) return null;
  const g = ((last - prev) / prev) * 100;
  if (g <= 0) return null;
  return pe / g;
}

// ── Data-driven insights / risk synthesis ────────────────────────────────────

interface InsightInput {
  periods: FundamentalPeriod[];
  latest: FundamentalPeriod | null;
  metrics: FundamentalMetric[];
  growth: GrowthSeries;
  netDebt: number | null;
  ebitda: number | null;
  fcf: number | null;
  marketCap: number | null;
  cash: number | null;
  totalDebt: number | null;
  equity: number | null;
  revenue: number | null;
  currency: string | null;
  primary: MetricSource;
}

function metricMap(metrics: FundamentalMetric[]): Map<string, FundamentalMetric> {
  return new Map(metrics.map((m) => [m.key, m]));
}

export function synthesizeInsights(input: InsightInput): FundamentalInsight[] {
  const out: FundamentalInsight[] = [];
  const m = metricMap(input.metrics);
  const latest = input.latest;
  if (!latest) return out;

  const revYoY = metricNum(m, 'revenueGrowth');
  const margin = metricNum(m, 'netMargin');
  const roic = metricNum(m, 'roic');
  const de = metricNum(m, 'debtToEquity');
  const netDebtToEbitda =
    input.netDebt !== null && input.ebitda && input.ebitda > 0 ? input.netDebt / input.ebitda : null;
  const interestCover =
    latest.operatingIncome !== null && latest.interestExpense !== null && latest.interestExpense !== 0
      ? Math.abs(latest.operatingIncome / latest.interestExpense)
      : null;

  // Revenue trend
  if (revYoY !== null) {
    out.push({
      id: 'revenue-trend',
      tone: revYoY >= 0.1 ? 'positive' : revYoY < 0 ? 'negative' : 'neutral',
      title:
        revYoY >= 0.1
          ? `Revenue expanding ${(revYoY * 100).toFixed(1)}% YoY`
          : revYoY < 0
            ? `Revenue contracting ${(revYoY * 100).toFixed(1)}% YoY`
            : 'Revenue roughly flat YoY',
      detail: `Latest reporting period (${latest.endDate}) revenue ${
        revYoY >= 0 ? 'grew' : 'fell'
      } ${Math.abs(revYoY * 100).toFixed(1)}% versus the prior year.`,
      evidence: ['revenue', 'revenueGrowth'],
    });
  }

  // Multi-year compounding
  const rev3 = metricNum(m, 'revenueCagr3');
  if (rev3 !== null && input.periods.length >= 4) {
    out.push({
      id: 'compounding',
      tone: rev3 >= 0.08 ? 'positive' : rev3 < 0 ? 'negative' : 'neutral',
      title: `3Y revenue CAGR ${(rev3 * 100).toFixed(1)}%`,
      detail:
        rev3 >= 0.08
          ? 'Revenue has compounded at a healthy rate across the last three fiscal years.'
          : rev3 < 0
            ? 'Revenue has declined on a 3-year compounded basis.'
            : 'Revenue growth has been modest over three years.',
      evidence: ['revenueCagr3', 'revenue'],
    });
  }

  // Profitability quality
  if (margin !== null) {
    out.push({
      id: 'net-margin',
      tone: margin >= 0.15 ? 'positive' : margin < 0 ? 'negative' : 'neutral',
      title: `Net margin ${(margin * 100).toFixed(1)}%`,
      detail:
        margin < 0
          ? 'The company is unprofitable on a net basis in the latest period.'
          : `The company converts ${(margin * 100).toFixed(1)}% of revenue into net income.`,
      evidence: ['netMargin', 'netIncome'],
    });
  }

  // Return on capital
  if (roic !== null) {
    out.push({
      id: 'roic',
      tone: roic >= 0.1 ? 'positive' : roic < 0 ? 'negative' : 'warning',
      title: `ROIC ${(roic * 100).toFixed(1)}%`,
      detail:
        roic < 0
          ? 'Operating profit is negative relative to invested capital — value is being destroyed.'
          : roic < 0.1
            ? 'Return on invested capital is below a typical 10% hurdle; check competitive position.'
            : 'Return on invested capital is above a typical 10% hurdle.',
      evidence: ['roic', 'operatingIncome'],
    });
  }

  // Leverage
  if (netDebtToEbitda !== null) {
    out.push({
      id: 'leverage',
      tone: netDebtToEbitda <= 2 ? 'positive' : netDebtToEbitda <= 4 ? 'warning' : 'negative',
      title: `Net debt ${netDebtToEbitda.toFixed(1)}× EBITDA`,
      detail:
        netDebtToEbitda <= 2
          ? 'Leverage is conservative relative to earnings power.'
          : netDebtToEbitda <= 4
            ? 'Leverage is moderate — monitor refinancing risk if rates rise.'
            : 'Leverage is elevated; net debt exceeds four years of EBITDA.',
      evidence: ['netDebt', 'ebitda'],
    });
  } else if (de !== null) {
    out.push({
      id: 'leverage',
      tone: de <= 1 ? 'positive' : de <= 2 ? 'warning' : 'negative',
      title: `Debt / Equity ${de.toFixed(2)}`,
      detail:
        de > 2
          ? 'Debt materially exceeds shareholders’ equity — balance-sheet risk.'
          : 'Debt is within a moderate range relative to equity.',
      evidence: ['debtToEquity', 'debt'],
    });
  }

  // Interest coverage
  if (interestCover !== null) {
    out.push({
      id: 'interest-cover',
      tone: interestCover >= 6 ? 'positive' : interestCover >= 2 ? 'warning' : 'negative',
      title: `Interest cover ${interestCover.toFixed(1)}×`,
      detail:
        interestCover < 2
          ? 'Operating income barely covers interest expense — earnings are sensitive to rates.'
          : 'Operating income comfortably covers interest expense.',
      evidence: ['operatingIncome', 'interestExpense'],
    });
  }

  // Free-cash-flow quality
  if (input.fcf !== null && input.marketCap !== null && input.marketCap > 0) {
    const yieldPct = (input.fcf / input.marketCap) * 100;
    out.push({
      id: 'fcf-yield',
      tone: yieldPct >= 4 ? 'positive' : yieldPct < 0 ? 'negative' : 'neutral',
      title: `FCF yield ${yieldPct.toFixed(1)}%`,
      detail:
        input.fcf < 0
          ? 'Free cash flow is negative — the business is consuming cash after capital spending.'
          : 'Free cash flow provides a positive yield against the current market value.',
      evidence: ['freeCashFlow', 'fcfYield'],
    });
  }

  // Cash runway when unprofitable
  if (input.fcf !== null && input.fcf < 0 && input.cash !== null) {
    const runway = input.fcf !== 0 ? Math.abs(input.cash / input.fcf) : null;
    if (runway !== null && runway < 5) {
      out.push({
        id: 'cash-runway',
        tone: 'warning',
        title: `Cash runway ~${runway.toFixed(1)} years`,
        detail:
          'At the current free-cash burn rate, existing cash covers under five years of operations.',
        evidence: ['cash', 'freeCashFlow'],
      });
    }
  }

  return out;
}

function metricNum(map: Map<string, FundamentalMetric>, key: string): number | null {
  const v = map.get(key)?.value;
  return typeof v === 'number' && Number.isFinite(v) ? v : null;
}
