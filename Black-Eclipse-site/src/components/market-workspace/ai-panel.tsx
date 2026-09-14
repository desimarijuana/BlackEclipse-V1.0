'use client';

// ── AI Panel — contextual, deterministic market view ─────────────────────────
// Renders the AiMarketView produced from real OHLCV. Used both as a standalone
// workspace panel and as the collapsible AI drawer inside a chart panel.
// NEVER covers the chart: it lives beside it (drawer / side panel) or below it.

import React, { useMemo } from 'react';
import { Bot, Brain, ShieldAlert, TrendingDown, TrendingUp } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useChartBars } from '@/lib/chart/subscription-manager';
import { analyzeForAi, type AiMarketView } from '@/lib/market-workspace/ai-analysis';
import { formatInstrumentPrice, instrumentMeta } from '@/lib/market-workspace/instruments';
import type { Timeframe } from '@/lib/chart/types';

type Tone = 'bull' | 'bear' | 'neutral' | 'warn';

const TONE_CLASS: Record<Tone, string> = {
  bull: 'text-emerald-400',
  bear: 'text-rose-400',
  neutral: 'text-foreground',
  warn: 'text-amber-400',
};

function Row({ label, value, tone = 'neutral' }: { label: string; value: string; tone?: Tone }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={cn('font-mono text-[11px] font-bold', TONE_CLASS[tone])}>{value}</span>
    </div>
  );
}

export interface AiPanelProps {
  symbol: string;
  market: string;
  timeframe?: Timeframe;
  /** Dense mode for small panels. */
  compact?: boolean;
  className?: string;
}

export function AiPanel({ symbol, market, timeframe = '1D', compact = false, className }: AiPanelProps) {
  const { data, loading } = useChartBars(symbol, market, timeframe);
  const meta = useMemo(() => instrumentMeta(symbol, market), [symbol, market]);
  const view = useMemo<AiMarketView | null>(
    () => (data ? analyzeForAi(symbol, data.bars) : null),
    [data, symbol],
  );

  if (loading && !data) {
    return <div className={cn('flex h-full items-center justify-center p-4 text-[11px] text-muted-foreground/70', className)}>Analyzing {symbol}…</div>;
  }
  if (!view) {
    return (
      <div className={cn('flex h-full flex-col items-center justify-center gap-2 p-4 text-center', className)}>
        <Brain size={20} className="text-muted-foreground/50" />
        <p className="text-[11px] text-muted-foreground/70 italic">Not enough price history to analyze {symbol}.</p>
      </div>
    );
  }

  const trendTone: Tone = view.trend === 'Bullish' ? 'bull' : view.trend === 'Bearish' ? 'bear' : 'neutral';
  const riskTone: Tone = view.risk === 'High' ? 'warn' : view.risk === 'Medium' ? 'neutral' : 'bull';

  return (
    <div className={cn('flex h-full flex-col overflow-y-auto scrollbar-hide', compact ? 'p-2' : 'p-3', className)}>
      <div className="mb-2 flex items-center gap-1.5">
        <Bot size={12} className="text-primary" />
        <span className="font-serif text-xs font-semibold text-foreground">AI Market View</span>
        <span className="ml-auto font-mono text-[9px] text-muted-foreground/60">{symbol} · {timeframe}</span>
      </div>

      <div className="rounded-xl border border-border/10 glass-card-subtle px-2.5 py-1.5">
        <Row
          label="Trend"
          value={view.trend}
          tone={trendTone}
        />
        <Row label="Structure" value={view.structure} />
        <Row label="Momentum" value={view.momentum} tone={view.momentum === 'Strong' ? 'bull' : 'neutral'} />
        <Row label="Volume" value={view.volume} />
        <Row label="Risk" value={view.risk} tone={riskTone} />
      </div>

      {view.levels.length > 0 && (
        <div className="mt-2">
          <span className="mb-1 block text-[9px] font-bold uppercase tracking-widest text-muted-foreground">Key Levels</span>
          <div className="flex flex-wrap gap-1">
            {view.levels.map((lv) => (
              <span key={lv} className="rounded-md border border-border/20 bg-accent/30 px-1.5 py-0.5 font-mono text-[10px] text-foreground/90">
                {formatInstrumentPrice(meta, lv)}
              </span>
            ))}
          </div>
        </div>
      )}

      {!compact && (
        <div className="mt-2 flex items-start gap-1.5 rounded-xl border border-primary/15 bg-primary/[0.04] px-2.5 py-2">
          {view.trend === 'Bearish' ? <TrendingDown size={12} className="mt-0.5 shrink-0 text-rose-400" /> : view.trend === 'Bullish' ? <TrendingUp size={12} className="mt-0.5 shrink-0 text-emerald-400" /> : <ShieldAlert size={12} className="mt-0.5 shrink-0 text-amber-400" />}
          <div>
            <span className="block text-[9px] font-bold uppercase tracking-widest text-primary/80">Summary</span>
            <p className="mt-0.5 text-[10px] leading-snug text-muted-foreground">{view.summary}</p>
          </div>
        </div>
      )}

      {!view.confident && (
        <p className="mt-2 text-[9px] italic text-amber-400/80">Limited history — treat this read with caution.</p>
      )}
    </div>
  );
}
