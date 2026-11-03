'use client';

// ── Journal Analytics — dimensional performance breakdown ─────────────────────

import React, { useMemo } from 'react';
import type { DimensionRow, JournalAnalytics, TradeRecord } from '@/lib/journal/types';
import { hasRBasis } from '@/lib/journal/trade-math';
import { DimensionBarChart, RDistributionChart, EquityCurveChart, ScatterChart, RollingMetricsChart, fmtR } from './charts';

interface AnalyticsProps {
  analytics: JournalAnalytics | null;
  trades: TradeRecord[];
}

export function JournalAnalyticsView({ analytics, trades }: AnalyticsProps) {
  const rValues = useMemo(
    () => trades.filter((t) => t.status === 'closed' && hasRBasis(t)).map((t) => t.rMultiple),
    [trades],
  );

  if (!analytics) {
    return <EmptyState />;
  }

  const rAvailable = analytics.performance.rAvailable;
  const basis: 'R' | 'pnl' = rAvailable ? 'R' : 'pnl';
  const basisHint = (suffix = '') => (rAvailable ? `NET R${suffix}` : `NET P&L${suffix}`);

  // Monthly returns reuse the DimensionRow bar chart shape.
  const monthlyRows: DimensionRow[] = analytics.monthlyReturns.map((m) => ({
    key: m.month,
    trades: m.trades,
    wins: Math.round(m.winRate * m.trades),
    losses: m.trades - Math.round(m.winRate * m.trades),
    winRate: m.winRate,
    netR: m.netR,
    netPnl: m.netPnl,
    expectancy: m.trades > 0 ? m.netR / m.trades : 0,
    profitFactor: 0,
  }));

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-2xl glass-card p-4">
        <EquityCurveChart equity={rAvailable ? analytics.equity : analytics.equityCurrency} currency={!rAvailable} height={260} />
      </div>

      {/* Depth analytics (Phase 4) */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={monthlyRows} title="Monthly Returns" hint={basisHint(' / MONTH')} basis={basis} height={Math.max(160, monthlyRows.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <RollingMetricsChart rolling={analytics.rolling} height={Math.max(160, monthlyRows.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <ScatterChart
            points={analytics.mfeMae.map((p) => ({ x: p.mae, y: p.mfe, label: p.label }))}
            xLabel="MAE (R)"
            yLabel="MFE (R)"
            title="MAE / MFE Efficiency"
            hint="FAVOURABLE VS ADVERSE EXCURSION"
            xFormatter={(v) => `${v.toFixed(1)}R`}
            yFormatter={(v) => `${v.toFixed(1)}R`}
            tooltipFormatter={(p) => `${p.label}<br/>MFE: <b>${fmtR(p.y)}</b><br/>MAE: <b>${fmtR(p.x)}</b>`}
            height={220}
          />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <ScatterChart
            points={analytics.confidenceScatter.map((p) => ({ x: p.confidence, y: p.rMultiple }))}
            xLabel="Confidence (1-5)"
            yLabel="R"
            title="Confidence vs Outcome"
            hint="EACH DOT = A TRADE"
            xFormatter={(v) => String(v)}
            yFormatter={(v) => `${v.toFixed(1)}R`}
            tooltipFormatter={(p) => `Confidence: <b>${p.x}</b><br/>Result: <b>${fmtR(p.y)}</b>`}
            height={220}
          />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.durationBuckets} title="By Holding Time" hint={basisHint()} basis={basis} height={Math.max(160, analytics.durationBuckets.length * 28)} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.bySymbol} title="By Symbol" hint={basisHint()} basis={basis} height={Math.max(160, analytics.bySymbol.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.bySetup} title="By Setup" hint={basisHint()} basis={basis} height={Math.max(160, analytics.bySetup.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.bySession} title="By Session" hint={basisHint()} basis={basis} height={Math.max(160, analytics.bySession.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byDayOfWeek} title="By Day of Week" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byDayOfWeek.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byHour} title="By Trading Hour (UTC)" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byHour.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byTimeframe} title="By Timeframe" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byTimeframe.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byDirection} title="By Direction" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byDirection.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byTrend} title="By Trend" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byTrend.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byRegime} title="By Market Regime" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byRegime.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byAccount} title="By Account" hint={basisHint()} basis={basis} height={Math.max(160, analytics.byAccount.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          <DimensionBarChart rows={analytics.byMagic} title="By Broker Magic" hint={basisHint(' · BROKER TRADES')} basis={basis} height={Math.max(160, analytics.byMagic.length * 28)} />
        </div>
        <div className="rounded-2xl glass-card p-4">
          {rAvailable ? (
            <RDistributionChart rValues={rValues} height={220} />
          ) : (
            <div className="flex h-[220px] flex-col items-center justify-center gap-1.5 text-center">
              <p className="font-mono text-[10px] uppercase tracking-widest font-bold text-muted-foreground">R Distribution</p>
              <p className="text-xs text-muted-foreground italic">UNAVAILABLE — no trade has a captured stop, so R cannot be measured.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-3xl glass-card p-12 text-center">
      <p className="text-sm text-muted-foreground">Add trades to see analytics.</p>
    </div>
  );
}
