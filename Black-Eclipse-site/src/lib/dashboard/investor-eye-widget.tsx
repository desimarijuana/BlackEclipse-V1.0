'use client';

// ── Investor Eye — Command Center widget ─────────────────────────────────────
// Surfaces the Investor Eye world-state (normalized, deduplicated events) inside
// the customizable dashboard grid. It is a thin view over the SAME DataHub state
// topics the full Investor Eye screen uses — one fetch path, no second cache, and
// no fabricated data. A failed/unavailable topic renders UNAVAILABLE, never a
// zero that reads as "nothing is happening".

import React, { useMemo } from 'react';
import { ScanEye } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useTopic } from '@/lib/workspace/data-hub';
import type { WidgetConfigField } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { IE_STATE_TOPIC } from '@/lib/investor-eye/topics';
import type { InvestorEyeState } from '@/lib/investor-eye/types';
import { SEVERITY_COLORS } from '@/lib/investor-eye/layers';
import { formatClock, formatEventTitle } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';

/** Time windows — the ids must match `registerStateTopic` windows in topics.ts. */
const HOURS: Record<string, number> = { '1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720 };

/**
 * Event lenses. `types: null` = no filter. A lens matches on event TYPE **or**
 * economic CHANNEL, the same rule the map layers use, so a channel-tagged event
 * is not dropped just because it was classified under a neighbouring type.
 */
const LENSES: Record<string, { types: string[] | null; channels: string[] | null }> = {
  all: { types: null, channels: null },
  conflict: { types: ['conflict', 'military', 'protest'], channels: ['Defense & Aerospace'] },
  energy: { types: ['energy'], channels: ['Energy'] },
  trade: { types: ['trade', 'tariff', 'shipping', 'sanction'], channels: ['Trade & Tariffs', 'Shipping & Logistics'] },
  disaster: { types: ['natural_disaster'], channels: null },
};

const TYPE_LABEL: Record<string, string> = {
  conflict: 'Conflict', military: 'Military', protest: 'Protest', sanction: 'Sanction',
  trade: 'Trade', tariff: 'Tariff', shipping: 'Shipping', energy: 'Energy',
  natural_disaster: 'Hazard', monetary: 'Monetary', fiscal: 'Fiscal',
  diplomatic: 'Diplomatic', election: 'Election', cyber: 'Cyber',
  regulatory: 'Regulatory', other: 'Other',
};

export const INVESTOR_EYE_RANGE_FIELD: WidgetConfigField = {
  key: 'range', label: 'Time window', type: 'select',
  options: [
    { value: '1h', label: 'Last hour' },
    { value: '6h', label: 'Last 6 hours' },
    { value: '24h', label: 'Last 24 hours' },
    { value: '7d', label: 'Last 7 days' },
    { value: '30d', label: 'Last 30 days' },
  ],
  default: '24h',
};

export const INVESTOR_EYE_LENS_FIELD: WidgetConfigField = {
  key: 'lens', label: 'Lens', type: 'select',
  options: [
    { value: 'all', label: 'All events' },
    { value: 'conflict', label: 'Conflict' },
    { value: 'energy', label: 'Energy' },
    { value: 'trade', label: 'Trade & sanctions' },
    { value: 'disaster', label: 'Hazards' },
  ],
  default: 'all',
};

function Dot({ source, loading }: { source: string; loading: boolean }) {
  const tone = loading ? 'bg-muted-foreground/50'
    : source === 'LIVE' ? 'bg-emerald-400'
    : source === 'CACHED' || source === 'HISTORICAL' ? 'bg-sky-400'
    : source === 'UNAVAILABLE' ? 'bg-red-500'
    : 'bg-amber-400';
  return <span className={cn('h-1.5 w-1.5 rounded-full', tone, source === 'LIVE' && !loading && 'animate-pulse')} />;
}

export function InvestorEyeWidget({ placement }: { placement: WidgetPlacement }) {
  const cfg = placement.config ?? {};
  const range = typeof cfg.range === 'string' && cfg.range in HOURS ? cfg.range : '24h';
  const lensId = typeof cfg.lens === 'string' && cfg.lens in LENSES ? cfg.lens : 'all';
  const hours = HOURS[range];

  // topics.ts registers a state topic for every window at module load, so this
  // id is always live — constructing it is pure (no fetch registration race).
  const topicId = `${IE_STATE_TOPIC}:${hours}`;
  const t = useTopic<InvestorEyeState>(topicId);
  const tz = useDisplayTimeZone();

  const events = t.data?.events ?? [];
  const lens = LENSES[lensId];
  const rows = useMemo(() => {
    const list = lens.types
      ? events.filter((e) => lens.types!.includes(e.eventType) || (lens.channels ?? []).some((c) => e.channels.includes(c)))
      : events;
    return [...list]
      .sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt))
      .slice(0, 14);
  }, [events, lens]);

  const critical = events.filter((e) => e.severity === 'critical' || e.severity === 'high').length;
  const countries = new Set(events.flatMap((e) => e.countries)).size;

  const loading = t.updatedAt === null;
  const unavailable = !loading && (t.source === 'UNAVAILABLE' || !t.data || t.data.eventsUnavailable === true);

  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
        <div className="flex min-w-0 items-center gap-1.5">
          <ScanEye size={13} className="shrink-0 text-primary" />
          <h3 className="font-serif text-sm font-semibold text-foreground truncate">Investor Eye</h3>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Dot source={t.source} loading={loading} />
          <span className="font-mono text-[9px] text-muted-foreground">{loading ? 'LOADING' : t.source}</span>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center text-center">
          <p className="text-xs italic text-muted-foreground/70">Loading world state…</p>
        </div>
      ) : unavailable ? (
        <div className="flex flex-1 items-center justify-center text-center">
          <p className="max-w-[26ch] text-xs italic text-amber-400/80">
            UNAVAILABLE — world-state feed not connected.
            {t.data?.lastKnownAt ? ` Last known ${formatClock(t.data.lastKnownAt, tz)}.` : ''}
          </p>
        </div>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[9px] font-mono text-muted-foreground">
            <span><span className="text-foreground">{events.length}</span> events</span>
            <span><span className="text-rose-400">{critical}</span> high/critical</span>
            <span><span className="text-foreground">{countries}</span> countries</span>
            <span className="ml-auto text-muted-foreground/70">{range.toUpperCase()}</span>
          </div>

          {rows.length === 0 ? (
            <div className="flex flex-1 items-center justify-center text-center">
              <p className="text-xs italic text-muted-foreground/70">No events in this window.</p>
            </div>
          ) : (
            <div className="flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto scrollbar-hide">
              {rows.map((e) => {
                const key = e.id ?? e.dedupKey;
                const sev = SEVERITY_COLORS[e.severity];
                return (
                  <div key={key} className="flex items-start gap-2 border-b border-border/5 pb-1.5 last:border-b-0">
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: sev }} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[9px] text-muted-foreground">{formatClock(e.publishedAt, tz)}</span>
                        <span
                          className="rounded-sm px-1 text-[8px] font-bold uppercase tracking-wide"
                          style={{ color: sev, backgroundColor: `${sev}1f` }}
                        >
                          {TYPE_LABEL[e.eventType] ?? e.eventType}
                        </span>
                        {e.sourceCount > 1 && (
                          <span className="font-mono text-[8px] text-muted-foreground/70">×{e.sourceCount}</span>
                        )}
                      </div>
                      <p className="mt-0.5 line-clamp-2 text-[10px] leading-snug text-foreground">
                        {e.headline ?? formatEventTitle(e.title, e.placeName)}
                      </p>
                      <p className="mt-0.5 truncate text-[9px] text-muted-foreground/70">
                        {e.countries.slice(0, 3).join(', ') || 'location unknown'}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
