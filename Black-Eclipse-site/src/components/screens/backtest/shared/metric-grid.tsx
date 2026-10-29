'use client';

// ── Shared metric grid ──────────────────────────────────────────────────────
// One definition of the performance tiles, used by the Backtest bench and the
// Strategy Studio. The runtime returns `metricDefinitions`; when it does, the
// tile explains itself instead of showing a bare number.

import React from 'react';
import { formatMetric } from '@/lib/backtest/backtest-client';
import { cn } from '@/lib/utils';

export interface MetricSpec {
  key: string;
  label: string;
}

export const DEFAULT_METRIC_CARDS: MetricSpec[] = [
  { key: 'total_return', label: 'Total Return' },
  { key: 'cagr', label: 'CAGR' },
  { key: 'max_drawdown', label: 'Max Drawdown' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'sharpe', label: 'Sharpe' },
  { key: 'sortino', label: 'Sortino' },
  { key: 'calmar', label: 'Calmar' },
  { key: 'win_rate', label: 'Win Rate' },
  { key: 'profit_factor', label: 'Profit Factor' },
  { key: 'trade_count', label: 'Trades' },
  { key: 'expectancy', label: 'Expectancy' },
  { key: 'avg_gross_exposure', label: 'Avg Exposure' },
];

/** The subset of the runtime's metric definition we render. */
export interface MetricDefinitionLike {
  definition?: string;
  unit?: string;
  method?: string;
}

export function MetricCard({
  name,
  label,
  value,
  definition,
}: {
  name: string;
  label: string;
  value: number | null | undefined;
  definition?: MetricDefinitionLike;
}) {
  const hint = definition?.definition
    ? `${definition.definition}${definition.method ? ` (${definition.method})` : ''}`
    : label;
  const negative = value != null && value < 0;
  return (
    <div
      className="glass-card-subtle rounded-xl px-3 py-2"
      data-metric={name}
      title={hint}
    >
      <p className="text-[9px] uppercase tracking-wider text-muted-foreground">{label}</p>
      <p
        className={cn(
          'mt-0.5 font-mono text-sm font-semibold text-foreground',
          negative && /(return|drawdown|cagr)/.test(name) && 'text-rose-400',
          value != null && value > 0 && /(return|cagr)/.test(name) && 'text-emerald-400',
        )}
      >
        {formatMetric(name, value)}
      </p>
    </div>
  );
}

export function MetricGrid({
  metrics,
  definitions,
  cards = DEFAULT_METRIC_CARDS,
}: {
  metrics: Record<string, number | null>;
  definitions?: Record<string, MetricDefinitionLike>;
  cards?: MetricSpec[];
}) {
  return (
    <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 lg:grid-cols-6">
      {cards.map((card) => (
        <MetricCard
          key={card.key}
          name={card.key}
          label={card.label}
          value={metrics[card.key]}
          definition={definitions?.[card.key]}
        />
      ))}
    </div>
  );
}

/** An expandable glossary, so "Calmar 0.7" is never an unexplained number. */
export function MetricDefinitions({ definitions }: { definitions?: Record<string, MetricDefinitionLike> }) {
  const entries = Object.entries(definitions ?? {}).filter(([, value]) => value?.definition);
  if (!entries.length) return null;
  return (
    <details className="mt-2 text-[11px] text-muted-foreground">
      <summary className="cursor-pointer select-none">What do these numbers mean?</summary>
      <dl className="mt-1 grid gap-1 sm:grid-cols-2">
        {entries.map(([name, value]) => (
          <div key={name} className="rounded-lg bg-black/20 px-2 py-1">
            <dt className="font-mono text-[10px] text-foreground">{name}</dt>
            <dd className="leading-relaxed">{value.definition}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
