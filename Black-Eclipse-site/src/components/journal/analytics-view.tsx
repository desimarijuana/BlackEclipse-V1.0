'use client';

// ── Journal Analytics — dimensional performance breakdown ─────────────────────

import React, { useMemo } from 'react';
import type { JournalAnalytics, TradeRecord } from '@/lib/journal/types';
import { DimensionBarChart, RDistributionChart, EquityCurveChart } from './charts';

interface AnalyticsProps {
  analytics: JournalAnalytics | null;
  trades: TradeRecord[];
}

export function JournalAnalyticsView({ analytics, trades }: AnalyticsProps) {
  const rValues = useMemo(
    () => trades.filter((t) => t.status === 'closed').map((t) => t.rMultiple),
    [trades],
  );

  if (!analytics) {
    return <EmptyState />;
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
        <EquityCurveChart equity={analytics.equity} height={260} />
      </div>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySymbol} title="By Symbol" hint="NET R" height={Math.max(160, analytics.bySymbol.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySetup} title="By Setup" hint="NET R" height={Math.max(160, analytics.bySetup.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.bySession} title="By Session" hint="NET R" height={Math.max(160, analytics.bySession.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byDayOfWeek} title="By Day of Week" hint="NET R" height={Math.max(160, analytics.byDayOfWeek.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byHour} title="By Trading Hour (UTC)" hint="NET R" height={Math.max(160, analytics.byHour.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byTimeframe} title="By Timeframe" hint="NET R" height={Math.max(160, analytics.byTimeframe.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byDirection} title="By Direction" hint="NET R" height={Math.max(160, analytics.byDirection.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byTrend} title="By Trend" hint="NET R" height={Math.max(160, analytics.byTrend.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byRegime} title="By Market Regime" hint="NET R" height={Math.max(160, analytics.byRegime.length * 28)} />
        </div>
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <RDistributionChart rValues={rValues} height={220} />
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-3xl bg-[#0f0f0f]/60 p-12 text-center">
      <p className="text-sm text-muted-foreground">Add trades to see analytics.</p>
    </div>
  );
}
