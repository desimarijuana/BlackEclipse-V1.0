'use client';

// ── Volume Analytics panel ───────────────────────────────────────────────────
// A turnover measuring tool for one market: what was actually traded, where the
// value concentrated, and how the market is distributed across contribution
// bands. Purely presentational — it renders the server's `VolumeSummary` (see
// `src/lib/heatmap.ts`) and never fabricates a figure. When the server reports
// no positive volume the panel says so instead of drawing a zeroed-out chart.

import React, { useMemo, useState } from 'react';
import { Activity, BarChart3, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { VolumeSummary } from '@/lib/heatmap';
/** Compact currency formatter (1.2B / 945.0M / 12.3K). */
function fmtCompact(v: number, currency: string): string {
  if (!Number.isFinite(v) || v <= 0) return '—';
  const prefix = currency && currency !== '$' ? `${currency} ` : '$';
  if (v >= 1e12) return `${prefix}${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${prefix}${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${prefix}${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${prefix}${(v / 1e3).toFixed(1)}K`;
  return `${prefix}${v.toFixed(2)}`;
}

/** Plain number formatter for share/notional counts. */
function fmtNumber(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return '—';
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

function pct(v: number): string {
  return `${v.toFixed(1)}%`;
}

/**
 * Concentration read from the HHI (0–10000). Standard competition thresholds:
 * >2500 highly concentrated, 1500–2500 moderate, <1500 competitive.
 */
function concentration(hhi: number): { label: string; tone: string; note: string } {
  if (hhi > 2500) {
    return {
      label: 'Highly concentrated',
      tone: 'text-amber-400',
      note: 'Turnover is dominated by a handful of instruments.',
    };
  }
  if (hhi > 1500) {
    return {
      label: 'Moderately concentrated',
      tone: 'text-sky-400',
      note: 'A few large instruments carry a meaningful share.',
    };
  }
  return {
    label: 'Competitive',
    tone: 'text-emerald-400',
    note: 'Turnover is spread fairly evenly across instruments.',
  };
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div
      className="glass-card-subtle rounded-xl border border-white/5 px-3 py-2.5"
      title={hint}
    >
      <div className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground/70">{label}</div>
      <div className="mt-0.5 font-mono text-sm font-bold text-foreground">{value}</div>
    </div>
  );
}

export function VolumeAnalyticsPanel({
  summary,
  marketLabel,
}: {
  summary: VolumeSummary;
  marketLabel: string;
}) {
  const [showAll, setShowAll] = useState(false);
  // `unit` is authoritative for how to label the raw total; never infer it.
  const rawLabel = summary.unit === 'notional' ? 'Quote notional' : 'Shares traded';
  const conc = useMemo(() => concentration(summary.hhi), [summary.hhi]);

  // Contributions are shown as a share bar; cap the bar so a dominant
  // instrument doesn't render a 100%-full track that looks like a bug.
  const maxShare = useMemo(
    () => Math.max(...summary.top.map(c => c.sharePct), 1),
    [summary.top],
  );

  const rows = showAll ? summary.top : summary.top.slice(0, 6);
  const hidden = Math.max(0, summary.top.length - rows.length);

  return (
    <div className="glass-card border border-white/5 rounded-3xl p-6 space-y-5 shrink-0">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/5 pb-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-primary/25 bg-primary/15">
            <BarChart3 className="text-primary" size={17} />
          </span>
          <div>
            <h2 className="font-serif text-lg font-semibold text-foreground">Volume Analytics</h2>
            <p className="text-[10px] text-muted-foreground font-mono">
              {marketLabel} · {summary.instruments} of {summary.marketAssets} instruments trading
            </p>
          </div>
        </div>
        <span
          className={cn('rounded-full border border-white/10 bg-black/30 px-2.5 py-1 text-[10px] font-bold', conc.tone)}
          title={conc.note}
        >
          {conc.label} · HHI {Math.round(summary.hhi)}
        </span>
      </div>

      {/* Headline figures */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        <StatTile
          label="Traded value"
          value={fmtCompact(summary.turnover, summary.currency)}
          hint={
            summary.unit === 'notional'
              ? 'Total 24h quote-currency notional traded across the market.'
              : 'Shares traded × price, summed across the market (traded value in market currency).'
          }
        />
        <StatTile label="Instruments" value={String(summary.instruments)} hint="Priced instruments with volume greater than zero." />
        <StatTile label="Average" value={fmtCompact(summary.averageTurnover, summary.currency)} hint="Mean traded value per instrument." />
        <StatTile label="Median" value={fmtCompact(summary.medianTurnover, summary.currency)} hint="Median traded value — robust to a single dominant instrument." />
        <StatTile label="Largest" value={fmtCompact(summary.maxTurnover, summary.currency)} hint="The single most-traded instrument's value." />
        <StatTile
          label="Top 10 share"
          value={pct(summary.top10SharePct)}
          hint="Percent of total market traded value held by the ten largest instruments."
        />
      </div>

      {/* Distribution across contribution bands */}
      <div>
        <div className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">
          <Activity size={11} /> Distribution by contribution
        </div>
        <div className="space-y-2">
          {summary.tiers.map(tier => (
            <div key={tier.label} className="flex items-center gap-3">
              <span className="w-36 shrink-0 text-[10px] font-semibold text-muted-foreground">{tier.label}</span>
              <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-white/[0.04]">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary/50 to-primary transition-all"
                  style={{ width: `${Math.min(100, tier.sharePct)}%` }}
                />
              </div>
              <span className="w-11 shrink-0 text-right font-mono text-[10px] font-bold text-foreground">
                {pct(tier.sharePct)}
              </span>
              <span className="w-14 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                {tier.count} {tier.count === 1 ? 'inst' : 'insts'}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-2 flex items-start gap-1.5 text-[9px] leading-relaxed text-muted-foreground/60">
          <Info size={10} className="mt-px shrink-0" />
          Bands are each instrument&apos;s share of {marketLabel} traded value, so they stay comparable across
          currencies. A dominant instrument can carry the majority of a market&apos;s value even when many
          instruments trade.
        </p>
      </div>

      {/* Top contributors */}
      <div>
        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground/80">
          Top contributors
        </div>
        <div className="space-y-1.5">
          {rows.map((c, i) => (
            <div
              key={c.symbol}
              className="relative flex items-center gap-3 overflow-hidden rounded-xl border border-white/5 bg-white/[0.015] px-3 py-2"
            >
              {/* Share bar behind the row */}
              <div
                className="absolute inset-y-0 left-0 bg-primary/[0.07]"
                style={{ width: `${(c.sharePct / maxShare) * 100}%` }}
                aria-hidden
              />
              <span className="relative w-5 shrink-0 font-mono text-[10px] text-muted-foreground/60">#{i + 1}</span>
              <span className="relative w-16 shrink-0 truncate font-mono text-[11px] font-bold text-primary">{c.symbol}</span>
              <span className="relative min-w-0 flex-1 truncate text-[10px] text-muted-foreground">{c.name}</span>
              <span className="relative w-24 shrink-0 text-right font-mono text-[10px] text-muted-foreground">
                {fmtNumber(c.volume)} {summary.unit === 'notional' ? 'notional' : 'shs'}
              </span>
              <span className="relative w-20 shrink-0 text-right font-mono text-[11px] font-semibold text-foreground">
                {fmtCompact(c.turnover, summary.currency)}
              </span>
              <span className="relative w-12 shrink-0 text-right font-mono text-[10px] font-bold text-foreground">
                {pct(c.sharePct)}
              </span>
            </div>
          ))}
        </div>
        {hidden > 0 && (
          <button
            onClick={() => setShowAll(true)}
            className="mt-2 cursor-pointer text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:text-primary transition-colors"
          >
            Show {hidden} more contributor{hidden === 1 ? '' : 's'}
          </button>
        )}
      </div>

      {/* Unit footnote — honesty about what the number means */}
      <p className="flex items-start gap-1.5 border-t border-white/5 pt-3 text-[9px] leading-relaxed text-muted-foreground/60">
        <Info size={10} className="mt-px shrink-0" />
        {summary.unit === 'notional'
          ? `Traded value is quote-currency notional (${summary.currency}); it is not multiplied by price.`
          : `Traded value is shares × price in ${summary.currency} (turnover). Raw ${rawLabel.toLowerCase()} are shown per instrument above.`}
      </p>
    </div>
  );
}
