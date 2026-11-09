'use client';

// ── Fundamentals panel (shared) ─────────────────────────────────────────────
// The presentational half of the fundamentals feature: the tabbed sections,
// metric tiles, charts and states. Extracted so the full Fundamentals screen AND
// the Market Screener detail popup render the SAME analysis from one source.
// Consumes only a normalized `FundamentalsSnapshot` — no provider knowledge.

import React, { useMemo, useState } from 'react';
import {
  Activity, ArrowUpRight, BarChart3, Building2, CalendarClock,
  Gauge, RefreshCw, ScrollText, TrendingUp,
} from '@/lib/icons';
import { FilingsSection } from './filings-section';
import { TabBar } from '@/components/ui/tab-bar';
import { useEChart, baseChartOption } from '@/components/screens/portfolio/use-echart';
import { useChartPalette } from '@/lib/chart-palette-store';
import { cn } from '@/lib/utils';
import type {
  FundamentalMetric,
  FundamentalsSnapshot,
  FundamentalPeriod,
  MetricSource,
} from '@/lib/fundamentals/types';
import {
  axisLabel, changeTone, fiscalLabel, fmtCompact, fmtMetricValue, fmtNumber,
  fmtPercent, TONE_CLASS, metricTone,
} from '@/lib/fundamentals/format';

export const FUNDAMENTAL_SECTIONS = [
  { id: 'overview', label: 'Overview', icon: Activity },
  { id: 'statements', label: 'Statements', icon: BarChart3 },
  { id: 'valuation', label: 'Valuation', icon: Gauge },
  { id: 'timeline', label: 'Timeline', icon: CalendarClock },
  { id: 'filings', label: 'Filings', icon: ScrollText },
] as const;
export type FundamentalSectionId = (typeof FUNDAMENTAL_SECTIONS)[number]['id'];

export const SOURCE_LABEL: Record<MetricSource, string> = {
  'sec-edgar': 'SEC EDGAR',
  financialmodelingprep: 'FMP',
  yahoo: 'Yahoo',
  'eclipse-filings': 'Eclipse Filings',
  derived: 'Derived',
};

export interface FundamentalsBodyProps {
  data: FundamentalsSnapshot;
  section: FundamentalSectionId;
  onSectionChange: (id: FundamentalSectionId) => void;
  /** Compact spacing for the modal popup. */
  compact?: boolean;
}

/** Tab bar + the active section. Shared by the screen and the screener popup. */
export function FundamentalsBody({ data, section, onSectionChange, compact }: FundamentalsBodyProps) {
  return (
    <div className={cn('flex flex-col', compact ? 'gap-4' : 'gap-6')}>
      <TabBar
        className="mb-0"
        items={FUNDAMENTAL_SECTIONS.map((s) => ({ id: s.id, label: s.label, icon: s.icon }))}
        activeId={section}
        onChange={(id) => onSectionChange(id as FundamentalSectionId)}
      />
      {section === 'overview' && <OverviewSection data={data} compact={compact} />}
      {section === 'statements' && <StatementsSection data={data} />}
      {section === 'valuation' && <ValuationSection data={data} />}
      {section === 'timeline' && <TimelineSection data={data} />}
      {section === 'filings' && <FilingsSection symbol={data.symbol} market={data.market} />}
    </div>
  );
}

// ── Full (single-page) fundamentals ─────────────────────────────────────────
// Renders every fundamentals section sequentially with no internal tab bar, for
// the single-page company detail experience (Sections D/E/F/H).
export function FundamentalsFull({ data, compact }: { data: FundamentalsSnapshot; compact?: boolean }) {
  return (
    <div className={cn('flex flex-col', compact ? 'gap-5' : 'gap-8')}>
      <section>
        <SectionHead title="Financial overview" desc="Signals and highlights derived from the reported statements." />
        <OverviewSection data={data} compact={compact} />
      </section>
      <section>
        <SectionHead title="Financial statements" desc="Income statement, balance sheet and cash flow by reported period." />
        <StatementsSection data={data} />
      </section>
      <section>
        <SectionHead title="Valuation" desc="Multiples and valuation inputs with sources and periods." />
        <ValuationSection data={data} />
      </section>
      <section>
        <SectionHead title="Disclosure timeline" desc="Filings and dated events the numbers came from." />
        <TimelineSection data={data} />
      </section>
      <section>
        <SectionHead title="SEC filings" desc="The filings index behind the statements — form, filed date, period and the primary document." />
        <FilingsSection symbol={data.symbol} market={data.market} />
      </section>
    </div>
  );
}

// ── Header ──────────────────────────────────────────────────────────────────

export function TickerHeader({ data }: { data: FundamentalsSnapshot }) {
  const price = data.quote?.price ?? null;
  const contributors = data.contributors.filter((c) => c !== 'derived');
  return (
    <section className="rounded-2xl glass-card border border-border/15 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono text-lg font-bold text-foreground">{data.symbol}</span>
            <span className="rounded-md border border-border/30 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
              {data.market}
            </span>
            <ProvenanceChip provenance={data.provenance} />
          </div>
          <p className="mt-1 text-sm text-muted-foreground truncate max-w-[52ch]">
            {data.company.name ?? 'Unknown issuer'}
            {data.company.sector ? ` · ${data.company.sector}` : ''}
            {data.company.industry ? ` · ${data.company.industry}` : ''}
          </p>
        </div>
        <div className="text-right">
          <p className="font-mono text-2xl font-bold text-foreground">
            {price !== null ? `$${fmtNumber(price, 2)}` : '—'}
          </p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {data.quote?.marketCap ? `Mkt cap ${fmtCompact(data.quote.marketCap)}` : ''}
          </p>
        </div>
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border/10 pt-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <Building2 size={12} /> Source: {contributors.map((c) => SOURCE_LABEL[c]).join(' + ') || 'unavailable'}
        </span>
        <span className="flex items-center gap-1.5">
          <CalendarClock size={12} /> Latest period: {fiscalLabel(data.fiscalYearEnd)}
        </span>
        <span className="flex items-center gap-1.5">
          <RefreshCw size={12} /> Updated {new Date(data.retrievedAt).toLocaleString()}
        </span>
        {data.currency && <span className="font-mono">{data.currency}</span>}
      </div>
    </section>
  );
}

function ProvenanceChip({ provenance }: { provenance: FundamentalsSnapshot['provenance'] }) {
  const map: Record<string, string> = {
    LIVE: 'border-emerald-400/30 text-emerald-400',
    CACHED: 'border-sky-400/30 text-sky-400',
    HISTORICAL: 'border-amber-400/30 text-amber-400',
    UNAVAILABLE: 'border-rose-400/30 text-rose-400',
  };
  return (
    <span className={cn('rounded-md border px-1.5 py-0.5 font-mono text-[9px] font-bold tracking-wide', map[provenance])}>
      {provenance}
    </span>
  );
}

// ── Overview ────────────────────────────────────────────────────────────────

function OverviewSection({ data, compact }: { data: FundamentalsSnapshot; compact?: boolean }) {
  const latest = data.periods[data.periods.length - 1] ?? null;
  return (
    <div className={cn('flex flex-col', compact ? 'gap-5' : 'gap-6')}>
      {data.insights.length > 0 && (
        <section>
          <SectionHead title="Signal" desc="Generated from the actual statements — each point names its evidence." />
          <div className={cn('grid gap-3', compact ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-2 xl:grid-cols-3')}>
            {data.insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} />
            ))}
          </div>
        </section>
      )}

      <section>
        <SectionHead title="Financial highlights" desc="Latest reported fiscal year, with YoY change and source for every figure." />
        <MetricGrid metrics={data.metrics} keys={OVERVIEW_KEYS} currency={data.currency} compact={compact} />
      </section>

      <section className={cn('grid grid-cols-1 gap-4', compact ? 'md:grid-cols-2' : 'xl:grid-cols-2')}>
        <ChartCard title="Revenue trend" hint={latest ? fiscalLabel(latest.endDate) : ''}>
          <RevenueChart data={data} />
        </ChartCard>
        <ChartCard title="EPS trend" hint={latest ? fiscalLabel(latest.endDate) : ''}>
          <SeriesChart periods={data.periods} field="eps" colorIndex={1} formatter={(v) => `$${fmtNumber(v, 2)}`} />
        </ChartCard>
        <ChartCard title="Free cash flow trend" hint={latest ? fiscalLabel(latest.endDate) : ''}>
          <SeriesChart periods={data.periods} field="freeCashFlow" colorIndex={2} formatter={(v) => fmtCompact(v)} />
        </ChartCard>
        <ChartCard title="Margin trend" hint="Gross · operating · net">
          <MarginChart data={data} />
        </ChartCard>
      </section>

      <section className={cn('grid grid-cols-1 gap-4', compact ? 'md:grid-cols-2' : 'xl:grid-cols-3')}>
        <ChartCard title="Debt vs cash" hint="Latest period">
          <DebtCashChart periods={data.periods} />
        </ChartCard>
        <ChartCard title="Historical valuation" hint="P/E · P/S · EV/EBITDA" className={compact ? '' : 'xl:col-span-2'}>
          <ValuationHistoryChart data={data} />
        </ChartCard>
      </section>
    </div>
  );
}

export const OVERVIEW_KEYS = [
  'revenue', 'grossProfit', 'operatingIncome', 'ebitda', 'netIncome', 'eps',
  'operatingCashFlow', 'capex', 'freeCashFlow',
  'grossMargin', 'operatingMargin', 'netMargin',
  'roe', 'roa', 'roic',
  'debt', 'netDebt', 'debtToEquity', 'currentRatio', 'quickRatio',
  'revenueGrowth', 'epsGrowth', 'fcfGrowth',
  'revenueCagr3', 'revenueCagr5',
];

// ── Statements ──────────────────────────────────────────────────────────────

function StatementsSection({ data }: { data: FundamentalsSnapshot }) {
  const [period, setPeriod] = useState<FundamentalPeriod | null>(data.periods[data.periods.length - 1] ?? null);
  const current = period ?? data.periods[data.periods.length - 1];
  if (!current) return <UnavailableState symbol={data.symbol} market={data.market} reason="No statement periods returned." />;

  const prior = data.periods[data.periods.indexOf(current) - 1] ?? null;
  return (
    <div className="flex flex-col gap-6">
      <TabBar
        variant="subtle"
        items={[...data.periods].reverse().map((p) => ({ id: p.endDate, label: fiscalLabel(p.endDate) }))}
        activeId={current.endDate}
        onChange={(id) => setPeriod(data.periods.find((p) => p.endDate === id) ?? current)}
      />

      <section className="rounded-2xl glass-card border border-border/15 overflow-hidden">
        <div className="grid grid-cols-3 gap-2 px-5 py-3 border-b border-border/10 text-[10px] uppercase tracking-widest font-bold text-muted-foreground">
          <span>Line item</span>
          <span className="text-right">{fiscalLabel(current.endDate)}</span>
          <span className="text-right">{fiscalLabel(prior?.endDate ?? current.endDate)}</span>
        </div>
        <StatementGroup
          title="Income statement"
          rows={[
            ['Revenue', current.revenue, prior?.revenue],
            ['Cost of revenue', current.costOfRevenue, prior?.costOfRevenue],
            ['Gross profit', current.grossProfit, prior?.grossProfit],
            ['Operating income', current.operatingIncome, prior?.operatingIncome],
            ['EBITDA (derived)', current.ebitda, prior?.ebitda],
            ['Net income', current.netIncome, prior?.netIncome],
            ['Diluted EPS', current.eps, prior?.eps, 'eps'],
          ]}
        />
        <StatementGroup
          title="Cash flow"
          rows={[
            ['Operating cash flow', current.operatingCashFlow, prior?.operatingCashFlow],
            ['Capital expenditure', current.capex, prior?.capex],
            ['Free cash flow', current.freeCashFlow, prior?.freeCashFlow],
            ['Dividends paid', current.dividendsPaid, prior?.dividendsPaid],
            ['Depreciation & amortization', current.depreciation, prior?.depreciation],
          ]}
        />
        <StatementGroup
          title="Balance sheet"
          rows={[
            ['Total assets', current.totalAssets, prior?.totalAssets],
            ['Total liabilities', current.totalLiabilities, prior?.totalLiabilities],
            ['Shareholders’ equity', current.totalEquity, prior?.totalEquity],
            ['Cash & equivalents', current.cash, prior?.cash],
            ['Total debt', current.totalDebt, prior?.totalDebt],
            ['Net debt', current.netDebt, prior?.netDebt],
            ['Current assets', current.currentAssets, prior?.currentAssets],
            ['Current liabilities', current.currentLiabilities, prior?.currentLiabilities],
          ]}
        />
        {current.filed && (
          <div className="px-5 py-3 border-t border-border/10 text-[10px] text-muted-foreground">
            Filed {current.filed}{current.form ? ` · ${current.form}` : ''} · source {SOURCE_LABEL[data.primarySource]}
          </div>
        )}
      </section>

      <section>
        <SectionHead title="Growth" desc="Compounded growth across the reported periods." />
        <MetricGrid
          metrics={data.metrics}
          keys={['revenueGrowth', 'epsGrowth', 'fcfGrowth', 'revenueCagr3', 'revenueCagr5', 'epsCagr3', 'fcfCagr3']}
          currency={data.currency}
        />
      </section>
    </div>
  );
}

function StatementGroup({
  title, rows,
}: {
  title: string;
  rows: Array<[string, number | null, number | null, ('eps' | 'usd')?]>;
}) {
  return (
    <div className="border-b border-border/10 last:border-b-0">
      <div className="px-5 py-2 bg-white/[0.015]">
        <span className="text-[10px] uppercase tracking-widest font-bold text-primary/80">{title}</span>
      </div>
      {rows.map(([label, value, prior, kind]) => {
        const tone = prior !== null && value !== null ? changeTone(value - prior) : 'flat';
        return (
          <div key={label} className="grid grid-cols-3 gap-2 px-5 py-2 hover:bg-white/[0.02] transition-colors">
            <span className="text-xs text-muted-foreground">{label}</span>
            <span className="text-right font-mono text-xs font-semibold text-foreground">
              {value === null ? '—' : kind === 'eps' ? `$${fmtNumber(value, 2)}` : fmtCompact(value)}
            </span>
            <span className={cn('text-right font-mono text-xs', TONE_CLASS[tone])}>
              {prior === null ? '—' : kind === 'eps' ? `$${fmtNumber(prior, 2)}` : fmtCompact(prior)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── Valuation ───────────────────────────────────────────────────────────────

const VALUATION_KEYS = [
  'pe', 'forwardPE', 'peg', 'ps', 'pb', 'evEbitda', 'evRevenue', 'fcfYield',
  'dividendRate', 'dividendYield', 'payoutRatio',
];

function ValuationSection({ data }: { data: FundamentalsSnapshot }) {
  const estimates = data.earnings.estimates;
  const history = data.earnings.history;
  return (
    <div className="flex flex-col gap-8">
      <section>
        <SectionHead title="Multiples" desc="Current valuation, with provider-reported figures preferred over derived ones." />
        <MetricGrid metrics={data.metrics} keys={VALUATION_KEYS} currency={data.currency} />
      </section>

      <section>
        <SectionHead title="Valuation history" desc="Price-to-earnings across reported years (price at each fiscal year end)." />
        <div className="rounded-2xl glass-card border border-border/15 p-4 h-72">
          <ValuationHistoryChart data={data} />
        </div>
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <div className="rounded-2xl glass-card border border-border/15 p-5">
          <SectionHead title="Earnings history" desc="Reported vs estimated EPS, most recent quarters." />
          <EarningsList rows={history} />
        </div>
        <div className="rounded-2xl glass-card border border-border/15 p-5">
          <SectionHead title="Estimates & ownership" desc="Analyst estimates where available; institutional and insider holdings otherwise." />
          {estimates.length > 0 && <EarningsList rows={estimates} estimateOnly />}
          <OwnershipBlock data={data} />
        </div>
      </section>
    </div>
  );
}

function EarningsList({ rows, estimateOnly }: { rows: FundamentalsSnapshot['earnings']['history']; estimateOnly?: boolean }) {
  const shown = [...rows].reverse().slice(0, 8);
  if (shown.length === 0) {
    return <p className="text-xs text-muted-foreground/70 italic py-4">No earnings {estimateOnly ? 'estimates' : 'history'} available from the configured providers.</p>;
  }
  return (
    <div className="flex flex-col">
      <div className="grid grid-cols-3 gap-2 py-1.5 text-[9px] uppercase tracking-widest font-bold text-muted-foreground border-b border-border/10">
        <span>Date</span><span className="text-right">Estimate</span><span className="text-right">Actual</span>
      </div>
      {shown.map((row) => (
        <div key={row.date} className="grid grid-cols-3 gap-2 py-1.5 border-b border-border/5 last:border-b-0">
          <span className="font-mono text-[11px] text-muted-foreground">{row.date}</span>
          <span className="text-right font-mono text-[11px] text-foreground">{row.estimate === null ? '—' : `$${fmtNumber(row.estimate, 2)}`}</span>
          <span className={cn('text-right font-mono text-[11px]', row.actual !== null && row.estimate !== null ? TONE_CLASS[changeTone(row.actual - row.estimate)] : 'text-foreground')}>
            {row.actual === null ? '—' : `$${fmtNumber(row.actual, 2)}`}
          </span>
        </div>
      ))}
    </div>
  );
}

function OwnershipBlock({ data }: { data: FundamentalsSnapshot }) {
  const o = data.ownership;
  if (!o) {
    return (
      <p className="mt-4 text-xs text-muted-foreground/70 italic">
        Ownership data unavailable from the configured providers.
      </p>
    );
  }
  const items: Array<[string, string]> = [
    ['Institutional', o.institutionalPercent === null ? '—' : fmtPercent(o.institutionalPercent)],
    ['Insider', o.insiderPercent === null ? '—' : fmtPercent(o.insiderPercent)],
    ['Short % float', o.shortPercentOfFloat === null ? '—' : fmtPercent(o.shortPercentOfFloat)],
    ['Shares short', o.sharesShort === null ? '—' : fmtCompact(o.sharesShort)],
  ];
  return (
    <div className="mt-4 grid grid-cols-2 gap-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg glass-card-subtle p-2.5">
          <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
          <p className="mt-0.5 font-mono text-sm font-bold text-foreground">{value}</p>
        </div>
      ))}
      <p className="col-span-2 text-[10px] text-muted-foreground/70">Source: {SOURCE_LABEL[o.source]}</p>
    </div>
  );
}

// ── Timeline ────────────────────────────────────────────────────────────────

function TimelineSection({ data }: { data: FundamentalsSnapshot }) {
  if (data.timeline.length === 0) {
    return <UnavailableState symbol={data.symbol} market={data.market} reason="No filing timeline available." />;
  }
  return (
    <section>
      <SectionHead title="Fundamental timeline" desc="Reported filings and provider events, newest first." />
      <div className="relative pl-4">
        <div className="absolute left-[5px] top-2 bottom-2 w-px bg-border/25" />
        {data.timeline.map((entry, i) => (
          <div key={`${entry.date}-${i}`} className="relative pl-5 pb-5 last:pb-0">
            <span className="absolute left-[-1px] top-1.5 h-2.5 w-2.5 rounded-full border border-primary/50 bg-primary/30" />
            <div className="rounded-xl glass-card-subtle border border-border/10 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs font-bold text-foreground">{entry.label}</span>
                <span className="font-mono text-[10px] text-muted-foreground">{entry.date}</span>
              </div>
              {entry.detail && <p className="mt-1 text-[11px] text-muted-foreground">{entry.detail}</p>}
              {entry.url && (
                <a href={entry.url} target="_blank" rel="noreferrer" className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-primary hover:underline">
                  View filing <ArrowUpRight size={10} />
                </a>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6">
        <SectionHead title="Company" desc="Profile from the provider layer." />
        <div className="rounded-2xl glass-card border border-border/15 p-5 grid grid-cols-2 md:grid-cols-4 gap-3">
          <ProfileItem label="Sector" value={data.company.sector} />
          <ProfileItem label="Industry" value={data.company.industry} />
          <ProfileItem label="Country" value={data.company.country} />
          <ProfileItem label="Employees" value={data.company.employees ? data.company.employees.toLocaleString() : null} />
        </div>
        {data.company.description && (
          <p className="mt-3 text-[12px] leading-relaxed text-muted-foreground max-w-[80ch]">{data.company.description}</p>
        )}
      </div>
    </section>
  );
}

function ProfileItem({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="rounded-lg glass-card-subtle p-3">
      <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm text-foreground">{value ?? '—'}</p>
    </div>
  );
}

// ── Charts ──────────────────────────────────────────────────────────────────

function useChartColors() {
  const palette = useChartPalette();
  return { primary: palette.lines.primary, series: palette.lines.series };
}

function RevenueChart({ data }: { data: FundamentalsSnapshot }) {
  const { primary } = useChartColors();
  const periods = data.periods;
  const has = periods.some((p) => p.revenue !== null);
  const ref = useEChart(() => {
    if (!has) return null;
    return {
      ...baseChartOption(),
      grid: { left: 6, right: 6, top: 12, bottom: 0, containLabel: true },
      xAxis: axisCategory(periods),
      yAxis: axisValue((v) => fmtCompact(v)),
      series: [{
        name: 'Revenue', type: 'bar', data: periods.map((p) => p.revenue),
        itemStyle: { color: primary, borderRadius: [4, 4, 0, 0] },
      }],
    };
  }, [has, periods, primary]);
  return has ? <div ref={ref} className="h-56" /> : <ChartEmpty />;
}

type ScalarField = 'eps' | 'freeCashFlow' | 'revenue' | 'operatingCashFlow' | 'netIncome';

function SeriesChart({
  periods, field, colorIndex, formatter,
}: {
  periods: FundamentalPeriod[];
  field: ScalarField;
  colorIndex: number;
  formatter: (v: number) => string;
}) {
  const { series, primary } = useChartColors();
  const color = colorIndex === 0 ? primary : series[(colorIndex - 1) % series.length] ?? primary;
  const has = periods.some((p) => p[field] !== null);
  const ref = useEChart(() => {
    if (!has) return null;
    return {
      ...baseChartOption(),
      grid: { left: 6, right: 6, top: 12, bottom: 0, containLabel: true },
      xAxis: axisCategory(periods),
      yAxis: axisValue(formatter),
      series: [{
        name: field, type: 'line', smooth: true, showSymbol: true,
        data: periods.map((p) => p[field] as number | null),
        lineStyle: { width: 2, color }, itemStyle: { color },
        areaStyle: { color, opacity: 0.08 },
      }],
    };
  }, [has, periods, field, color]);
  return has ? <div ref={ref} className="h-56" /> : <ChartEmpty />;
}

function MarginChart({ data }: { data: FundamentalsSnapshot }) {
  const { primary, series } = useChartColors();
  const periods = data.periods;
  const has = periods.some((p) => p.grossMargin !== null);
  const ref = useEChart(() => {
    if (!has) return null;
    return {
      ...baseChartOption(),
      grid: { left: 6, right: 6, top: 20, bottom: 0, containLabel: true },
      legend: { top: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
      xAxis: axisCategory(periods),
      yAxis: { ...axisValue((v) => `${(v * 100).toFixed(0)}%`) },
      series: [
        { name: 'Gross', type: 'line', smooth: true, showSymbol: false, data: periods.map((p) => p.grossMargin), lineStyle: { color: primary } },
        { name: 'Operating', type: 'line', smooth: true, showSymbol: false, data: periods.map((p) => p.operatingMargin), lineStyle: { color: series[0] ?? primary } },
        { name: 'Net', type: 'line', smooth: true, showSymbol: false, data: periods.map((p) => p.netMargin), lineStyle: { color: series[1] ?? primary } },
      ],
    };
  }, [has, periods, primary, series]);
  return has ? <div ref={ref} className="h-56" /> : <ChartEmpty />;
}

function DebtCashChart({ periods }: { periods: FundamentalPeriod[] }) {
  const { series, primary } = useChartColors();
  const has = periods.some((p) => p.totalDebt !== null || p.cash !== null);
  const ref = useEChart(() => {
    if (!has) return null;
    return {
      ...baseChartOption(),
      grid: { left: 6, right: 6, top: 20, bottom: 0, containLabel: true },
      legend: { top: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
      xAxis: axisCategory(periods),
      yAxis: axisValue((v) => fmtCompact(v)),
      series: [
        { name: 'Debt', type: 'bar', data: periods.map((p) => p.totalDebt), itemStyle: { color: series[2] ?? '#fb7185', borderRadius: [3, 3, 0, 0] } },
        { name: 'Cash', type: 'bar', data: periods.map((p) => p.cash), itemStyle: { color: primary, borderRadius: [3, 3, 0, 0] } },
      ],
    };
  }, [has, periods, primary, series]);
  return has ? <div ref={ref} className="h-56" /> : <ChartEmpty />;
}

export function ValuationHistoryChart({ data }: { data: FundamentalsSnapshot }) {
  const { primary, series } = useChartColors();
  const price = data.quote?.price ?? null;
  const shares = data.quote?.sharesOutstanding ?? null;
  // Reconstruct a rough per-year multiple from the current price and reported
  // fundamentals. Clearly labeled as an approximation; absent inputs → no chart.
  const points = useMemo(
    () =>
      data.periods
        .map((p) => {
          const pe = price !== null && p.eps && p.eps > 0 ? price / p.eps : null;
          const ps = shares !== null && p.revenue && p.revenue > 0 ? (price! * shares) / p.revenue : null;
          const evEbitda = p.ebitda && p.ebitda > 0 && data.quote?.enterpriseValue ? data.quote.enterpriseValue / p.ebitda : null;
          return { period: p.endDate, pe, ps, evEbitda };
        })
        .filter((p) => p.pe !== null || p.ps !== null || p.evEbitda !== null),
    [data.periods, data.quote?.enterpriseValue, price, shares]
  );
  const has = points.length > 0;
  const ref = useEChart(() => {
    if (!has) return null;
    const labels = points.map((p) => axisLabel(p.period));
    return {
      ...baseChartOption(),
      grid: { left: 6, right: 6, top: 20, bottom: 0, containLabel: true },
      legend: { top: 0, textStyle: { color: '#94a3b8', fontSize: 9 }, itemWidth: 12 },
      xAxis: { type: 'category', data: labels, axisLabel: { color: '#94a3b8', fontSize: 9 }, axisLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } } },
      yAxis: axisValue((v) => `${fmtNumber(v, 0)}×`),
      series: [
        { name: 'P/E', type: 'line', smooth: true, showSymbol: false, data: points.map((p) => p.pe), lineStyle: { color: primary } },
        { name: 'P/S', type: 'line', smooth: true, showSymbol: false, data: points.map((p) => p.ps), lineStyle: { color: series[0] ?? primary } },
        { name: 'EV/EBITDA', type: 'line', smooth: true, showSymbol: false, data: points.map((p) => p.evEbitda), lineStyle: { color: series[1] ?? primary } },
      ],
    };
  }, [has, points, primary, series]);
  if (!has) return <ChartEmpty />;
  return (
    <div className="flex flex-col h-full">
      <div ref={ref} className="h-56 flex-1" />
      <p className="mt-2 text-[10px] text-muted-foreground/70">
        Approximate: current {price !== null ? `$${fmtNumber(price, 2)}` : 'price'} applied to each year’s reported EPS/revenue. Not a historical price series.
      </p>
    </div>
  );
}

function axisCategory(periods: FundamentalPeriod[]) {
  return {
    type: 'category' as const,
    data: periods.map((p) => axisLabel(p.endDate)),
    axisLabel: { color: '#94a3b8', fontSize: 9 },
    axisLine: { lineStyle: { color: 'rgba(148,163,184,0.1)' } },
  };
}

function axisValue(formatter: (v: number) => string) {
  return {
    type: 'value' as const,
    scale: true,
    splitLine: { lineStyle: { color: 'rgba(148,163,184,0.05)' } },
    axisLabel: { color: '#94a3b8', fontSize: 9, formatter: (v: number) => formatter(v) },
  };
}

// ── Shared pieces ───────────────────────────────────────────────────────────

export function MetricGrid({
  metrics, keys, currency, compact,
}: {
  metrics: FundamentalMetric[];
  keys: string[];
  currency: string | null;
  compact?: boolean;
}) {
  const byKey = useMemo(() => new Map(metrics.map((m) => [m.key, m])), [metrics]);
  const shown = keys.map((k) => byKey.get(k)).filter((m): m is FundamentalMetric => Boolean(m));
  return (
    <div className={cn('grid gap-2.5', compact ? 'grid-cols-2 md:grid-cols-3' : 'grid-cols-2 md:grid-cols-3 xl:grid-cols-5')}>
      {shown.map((metric) => (
        <MetricTile key={metric.key} metric={metric} currency={currency} />
      ))}
    </div>
  );
}

function MetricTile({ metric, currency }: { metric: FundamentalMetric; currency: string | null }) {
  const hasValue = metric.value !== null;
  const tone = metric.yoy !== null ? changeTone(metric.yoy) : (hasValue ? metricTone(metric) : 'flat');
  return (
    <div className="group flex min-w-0 flex-col rounded-xl glass-card-subtle border border-border/10 p-3" title={metric.ref?.label}>
      <div className="flex items-start justify-between gap-1">
        <p className="text-[9px] uppercase tracking-widest font-bold text-muted-foreground truncate">{metric.label}</p>
        <span className="shrink-0 rounded border border-border/25 px-1 py-px font-mono text-[8px] text-muted-foreground/80">
          {SOURCE_LABEL[metric.source]}
        </span>
      </div>
      <p className={cn('mt-1.5 font-mono text-base font-bold truncate', hasValue ? TONE_CLASS[tone] : 'text-muted-foreground/50')}>
        {fmtMetricValue(metric.value, metric.unit, currency)}
      </p>
      <div className="mt-0.5 flex items-center justify-between gap-1">
        <span className="font-mono text-[9px] text-muted-foreground/70 truncate">{metric.period ? fiscalLabel(metric.period) : '—'}</span>
        {metric.yoy !== null && (
          <span className={cn('font-mono text-[9px] font-semibold', TONE_CLASS[changeTone(metric.yoy)])}>
            {metric.yoy > 0 ? '+' : ''}{fmtPercent(metric.yoy)}
          </span>
        )}
      </div>
    </div>
  );
}

function InsightCard({ insight }: { insight: FundamentalsSnapshot['insights'][number] }) {
  const tone: Record<string, string> = {
    positive: 'border-emerald-400/25 text-emerald-400',
    negative: 'border-rose-400/25 text-rose-400',
    warning: 'border-amber-400/25 text-amber-400',
    neutral: 'border-border/25 text-muted-foreground',
  };
  const Icon = insight.tone === 'positive' ? TrendingUp : insight.tone === 'negative' ? Activity : Gauge;
  return (
    <div className={cn('rounded-xl glass-card-subtle border p-3.5', tone[insight.tone])}>
      <div className="flex items-center gap-2">
        <Icon size={13} />
        <span className="text-xs font-bold">{insight.title}</span>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground">{insight.detail}</p>
      <p className="mt-2 font-mono text-[9px] text-muted-foreground/60">Evidence: {insight.evidence.join(', ')}</p>
    </div>
  );
}

function ChartCard({
  title, hint, children, className,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('rounded-2xl glass-card border border-border/15 p-4', className)}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <h3 className="font-serif text-sm font-semibold text-foreground">{title}</h3>
        {hint && <span className="font-mono text-[9px] text-muted-foreground/70">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function SectionHead({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="mb-4">
      <p className="text-[13px] font-semibold uppercase tracking-[0.05em] text-foreground">{title}</p>
      <p className="text-[12px] text-muted-foreground mt-1 max-w-[70ch] leading-relaxed">{desc}</p>
      <div className="mt-3 h-px bg-border/20" />
    </div>
  );
}

function ChartEmpty() {
  return (
    <div className="flex h-56 items-center justify-center">
      <p className="text-xs text-muted-foreground/60 italic">No series data from the configured providers.</p>
    </div>
  );
}

export function LoadingState() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-2.5">
        {Array.from({ length: 10 }).map((_, i) => (
          <div key={i} className="h-20 rounded-xl glass-card-subtle animate-pulse" />
        ))}
      </div>
      <div className="h-64 rounded-2xl glass-card animate-pulse" />
      <p className="text-center text-xs text-muted-foreground">Pulling filings and market data…</p>
    </div>
  );
}

export function UnavailableState({ symbol, market, reason }: { symbol: string; market: string; reason: string | null }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl glass-card border border-border/15 py-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-border/25 bg-white/[0.02]">
        <BarChart3 size={22} className="text-muted-foreground" />
      </div>
      <p className="font-mono text-sm font-bold text-foreground">UNAVAILABLE</p>
      <p className="max-w-[46ch] text-xs text-muted-foreground leading-relaxed">
        No fundamentals for <span className="font-mono">{symbol}</span> ({market}). {reason ?? ''}
      </p>
      <p className="text-[10px] text-muted-foreground/60 max-w-[52ch]">
        SEC EDGAR covers US issuers; Yahoo covers global markets when the optional Python bridge is installed. Nothing is fabricated when a source is missing.
      </p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl glass-card border border-border/15 py-12 text-center">
      <p className="text-xs text-rose-400">{message}</p>
      <button
        onClick={onRetry}
        className="rounded-xl glass-card-subtle border border-border/20 px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-accent/40 cursor-pointer"
      >
        Retry
      </button>
    </div>
  );
}
