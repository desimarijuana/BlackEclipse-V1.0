'use client';

// ── Investor Eye — Historical Analogues panel (Phase 2.9, spec §38) ──────────
// Calls the existing `/api/investor-eye/analogues` endpoint (previously unused)
// for the selected event and renders:
//   - the years in which the same event TYPE clustered (real stored events),
//   - the actual stored close series for a requested symbol, if any.
//
// Honesty rules baked into the UI: sample size and date range are always shown,
// missing series renders UNAVAILABLE (never a synthetic curve), and the
// disclaimer is rendered verbatim — a past move is not a prediction.

import { useEffect, useState } from 'react';
import { Loader2, TrendingUp } from '@/lib/icons';
import type { Provenance } from '@/lib/investor-eye/types';

interface AnaloguesResponse {
  available: boolean;
  note?: string;
  /** The instrument whose history is shown (resolved server-side). */
  symbol?: string | null;
  analogues?: {
    eventType: string;
    analoguePeriods: Array<{ label: string; eventCount: number }>;
    series?: Array<{ date: string; value: number }>;
    seriesLabel?: string;
    sampleSize: number;
    dateRange: { from: string; to: string } | null;
    availability: Provenance;
    disclaimer: string;
  };
}

export function AnaloguesPanel({
  eventId,
  eventType,
  symbol,
}: {
  eventId: string;
  eventType: string;
  symbol?: string;
}) {
  const [data, setData] = useState<AnaloguesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = new URLSearchParams({ id: eventId });
    if (symbol) qs.set('symbol', symbol);
    fetch(`/api/investor-eye/analogues?${qs.toString()}`)
      .then((r) => r.json())
      .then((json: AnaloguesResponse) => { if (!cancelled) setData(json); })
      .catch(() => { if (!cancelled) setData({ available: false, note: 'Historical data unavailable.' }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eventId, symbol]);

  const analogues = data?.analogues;
  const maxPeriod = Math.max(1, ...(analogues?.analoguePeriods ?? []).map((p) => p.eventCount));

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <TrendingUp size={11} className="text-muted-foreground" />
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Historical Analogues
        </span>
        <span className="text-[9px] font-mono text-muted-foreground/60">{eventType.replace(/_/g, ' ')}</span>
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
          <Loader2 size={11} className="animate-spin" /> Loading…
        </div>
      )}

      {!loading && !data?.available && (
        <div className="text-[10px] italic text-muted-foreground/70">
          {data?.note ?? 'No historical context available.'}
        </div>
      )}

      {!loading && data?.available && analogues && (
        <>
          {analogues.analoguePeriods.length === 0 ? (
            <div className="text-[10px] italic text-muted-foreground/70">
              No prior periods of this event type are stored yet.
            </div>
          ) : (
            <div className="space-y-1">
              {analogues.analoguePeriods.slice(-8).map((p) => (
                <div key={p.label} className="flex items-center gap-2 text-[10px]">
                  <span className="w-10 shrink-0 font-mono text-muted-foreground">{p.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                    <div
                      className="h-full rounded-full bg-violet-400/70"
                      style={{ width: `${Math.max(4, (p.eventCount / maxPeriod) * 100)}%` }}
                    />
                  </div>
                  <span className="w-6 shrink-0 text-right font-mono text-foreground">{p.eventCount}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-2 border-t border-border/10 pt-1.5">
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-muted-foreground">
                {analogues.seriesLabel ? `${analogues.seriesLabel} history` : data?.symbol ? `${data.symbol} history` : 'Market history'}
              </span>
              <span className="font-mono text-muted-foreground/70">
                n={analogues.sampleSize}
                {analogues.dateRange ? ` · ${analogues.dateRange.from}→${analogues.dateRange.to}` : ''}
              </span>
            </div>
            {analogues.availability === 'UNAVAILABLE' || !analogues.series?.length ? (
              <div className="mt-1 text-[10px] italic text-muted-foreground/70">
                No stored price history for this instrument — unavailable rather than simulated.
              </div>
            ) : (
              <Sparkline series={analogues.series} />
            )}
          </div>

          <div className="mt-1.5 text-[9px] italic leading-relaxed text-muted-foreground/60">
            {analogues.disclaimer}
          </div>
        </>
      )}
    </div>
  );
}

/** Minimal inline SVG sparkline from the real stored series (no chart deps). */
function Sparkline({ series }: { series: Array<{ date: string; value: number }> }) {
  const values = series.map((p) => p.value).filter((v) => Number.isFinite(v));
  if (values.length < 2) {
    return <div className="mt-1 text-[10px] italic text-muted-foreground/70">Insufficient history.</div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const W = 260;
  const H = 40;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * W;
      const y = H - ((v - min) / span) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const rising = values[values.length - 1] >= values[0];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 h-10 w-full" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={rising ? '#34d399' : '#f87171'}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
