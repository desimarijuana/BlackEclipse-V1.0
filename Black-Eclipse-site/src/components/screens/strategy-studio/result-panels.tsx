'use client';

// ── Strategy Studio results ─────────────────────────────────────────────────
// The performance / curve / trade panels for one backtest. Every number is the
// runtime's; an empty curve or zero trades is shown as-is. The Edge Report is a
// separate full-width panel so its figures have room.

import React from 'react';
import { EquityChart, DrawdownChart } from '@/components/screens/backtest/shared/charts';
import { MetricGrid, MetricDefinitions } from '@/components/screens/backtest/shared/metric-grid';
import { TradeTable } from '@/components/screens/backtest/shared/trade-table';
import type { BacktestResult } from '@/lib/backtest/backtest-client';
import { Activity, LineChart, Loader2, TrendingUp } from '@/lib/icons';

export function ResultPanels({
  result,
  grading,
  onGrade,
}: {
  result: BacktestResult;
  grading: boolean;
  onGrade: () => void;
}) {
  return (
    <>
      <div className="glass-card rounded-2xl p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <TrendingUp className="h-4 w-4 text-primary" />
          <h2 className="text-sm font-semibold">Performance</h2>
          <span className="font-mono text-[10px] text-muted-foreground">
            {String((result.metadata.symbols as string[] | undefined)?.join(', ') ?? '')} |{' '}
            {String(result.metadata.interval ?? '')} | {String(result.observability.barsProcessed ?? '')} bars
            {result.experimentId ? ` | ${result.experimentId}` : ''}
          </span>
        </div>
        <MetricGrid metrics={result.metrics} definitions={result.metricDefinitions} />
        <MetricDefinitions definitions={result.metricDefinitions} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onGrade}
            disabled={grading}
            className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
            title="Grade the evidence behind this run (deterministic, not an AI opinion)"
          >
            {grading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
            Grade this edge
          </button>
          <span className="text-[10px] text-muted-foreground">Deterministic grade, not an AI opinion.</span>
        </div>
      </div>

      <div className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-xs font-semibold">Equity curve</h3>
        <EquityChart result={result} />
      </div>

      <div className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-xs font-semibold">Drawdown</h3>
        <DrawdownChart result={result} />
      </div>

      <div className="glass-card rounded-2xl p-4">
        <h3 className="mb-2 text-xs font-semibold">
          Trades <span className="text-muted-foreground">({result.trades.length})</span>
        </h3>
        <TradeTable result={result} />
      </div>

      {result.warnings.length ? (
        <div className="glass-card rounded-2xl p-4">
          <h3 className="mb-2 text-xs font-semibold">Warnings</h3>
          <ul className="space-y-1">
            {result.warnings.map((warning, index) => (
              <li key={`${warning.code}-${index}`} className="text-[11px] text-amber-200">
                <span className="font-mono text-[10px]">{warning.code}</span> {warning.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

export function EmptyResults() {
  return (
    <div className="glass-card flex min-h-[240px] flex-col items-center justify-center gap-2 rounded-2xl p-8 text-center">
      <LineChart className="h-8 w-8 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">
        Draft a strategy, then save and run it to see performance, risk and trades.
      </p>
    </div>
  );
}
