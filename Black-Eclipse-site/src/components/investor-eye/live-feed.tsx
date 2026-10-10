'use client';

// ── Investor Eye — Live Event Stream ─────────────────────────────────────────
// The compact, always-on feed beside the map. It answers "what is happening
// right now?" without requiring a click, and it is the surface that highlights
// CONFLICT coverage — the category the world-state map is most often asked
// about.
//
// Real data only: every row is a normalized event from the assembled world
// state, and its source links are the ones the sources actually reported. Rows
// are clickable and select the event on the map (spec §13).

import { useEffect, useMemo, useRef, useState } from 'react';
import { Radio } from '@/lib/icons';
import { DotGrid } from '@/components/ui/ascii-loader';
import type { NormalizedEvent } from '@/lib/investor-eye/types';
import { SEVERITY_COLORS } from '@/lib/investor-eye/layers';
import { formatClock, formatEventTitle } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import { useListNavigation } from '@/hooks/use-list-navigation';
import { useInvestorEyeStore } from '@/lib/investor-eye/store';
import { cn } from '@/lib/utils';

interface LiveFeedProps {
  events: NormalizedEvent[];
  onSelect: (event: NormalizedEvent) => void;
  /** Open the full dossier popup for the event (click / Enter). */
  onOpen?: (event: NormalizedEvent) => void;
  selectedKey?: string;
  /** True while the first world-state fetch is still in flight. */
  loading?: boolean;
  className?: string;
}

/**
 * Feed lenses.
 *
 * A lens matches on event TYPE **or** economic CHANNEL, the same rule the map
 * layers use (an event typed `conflict` that transmits through Shipping still
 * belongs in Shipping). Matching on type alone made "Energy"/"Trade" drop
 * channel-tagged events, so a lens could look broken when its events were
 * classified under a neighbouring type. `channels: null` disables channel
 * matching (used only by "All", which shows everything).
 */
const FILTERS: Array<{
  id: 'conflict' | 'all' | 'energy' | 'trade' | 'disaster';
  label: string;
  types: string[] | null;
  channels: string[] | null;
}> = [
  { id: 'conflict', label: 'Conflict', types: ['conflict', 'military', 'protest'], channels: ['Defense & Aerospace'] },
  { id: 'all', label: 'All', types: null, channels: null },
  { id: 'energy', label: 'Energy', types: ['energy'], channels: ['Energy'] },
  { id: 'trade', label: 'Trade', types: ['trade', 'tariff', 'shipping', 'sanction'], channels: ['Trade & Tariffs', 'Shipping & Logistics'] },
  { id: 'disaster', label: 'Hazards', types: ['natural_disaster'], channels: null },
];

type FilterId = (typeof FILTERS)[number]['id'];

/** True when `event` belongs in `filter` by type OR channel. */
function matchesLens(event: NormalizedEvent, filter: (typeof FILTERS)[number]): boolean {
  if (!filter.types) return true;
  if (filter.types.includes(event.eventType)) return true;
  return (filter.channels ?? []).some((c) => event.channels.includes(c));
}

/** Event-type → short display label. */
const TYPE_LABEL: Record<string, string> = {
  conflict: 'Conflict',
  military: 'Military',
  protest: 'Protest',
  sanction: 'Sanction',
  trade: 'Trade',
  tariff: 'Tariff',
  shipping: 'Shipping',
  energy: 'Energy',
  natural_disaster: 'Hazard',
  monetary: 'Monetary',
  fiscal: 'Fiscal',
  diplomatic: 'Diplomatic',
  election: 'Election',
  cyber: 'Cyber',
  regulatory: 'Regulatory',
  other: 'Other',
};

export function LiveFeed({ events, onSelect, onOpen, selectedKey, loading = false, className }: LiveFeedProps) {
  const tz = useDisplayTimeZone();
  const [filter, setFilter] = useState<FilterId>('conflict');
  const rootRef = useRef<HTMLDivElement>(null);
  const clearSelection = useInvestorEyeStore((s) => s.clearSelection);

  const active = FILTERS.find((f) => f.id === filter) ?? FILTERS[0];

  const rows = useMemo(() => {
    const list = events.filter((e) => matchesLens(e, active));
    // Newest first; the state is already window-filtered by the timeline.
    return [...list].sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt)).slice(0, 60);
  }, [events, active]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const f of FILTERS) out[f.id] = events.filter((e) => matchesLens(e, f)).length;
    return out;
  }, [events]);

  const rowKeys = useMemo(() => rows.map((e) => e.id ?? e.dedupKey), [rows]);
  const selectRef = useRef(onSelect);
  const openRef = useRef(onOpen);
  useEffect(() => {
    selectRef.current = onSelect;
    openRef.current = onOpen;
  });
  const listNav = useListNavigation({
    ids: rowKeys,
    rootRef,
    enabled: !loading,
    shortcutPrefix: 'investor-eye.feed',
    // Enter (or a click) opens the full dossier popup.
    onOpen: (key) => {
      const event = rows.find((e) => (e.id ?? e.dedupKey) === key);
      if (event) openRef.current?.(event);
    },
    onSelectionChange: (key) => {
      const event = rows.find((e) => (e.id ?? e.dedupKey) === key);
      if (event) selectRef.current(event);
    },
    onEscape: () => clearSelection(),
  });

  useEffect(() => {
    listNav.select(selectedKey ?? null);
    // Only mirror the external map selection; local roving happens on keypress.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  return (
    <div ref={rootRef} className={cn('flex min-h-0 flex-col rounded-2xl border border-white/10 dark:border-white/5 glass-card', className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border/10 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Radio size={13} className="text-emerald-400" />
          <span className="text-[11px] font-bold uppercase tracking-widest text-foreground">Live Event Stream</span>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">{rows.length}</span>
      </div>

      {/* Lenses */}
      <div className="flex flex-wrap items-center gap-1 border-b border-border/10 px-3 py-1.5">
        {FILTERS.map((f) => {
          const on = filter === f.id;
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => setFilter(f.id)}
              aria-pressed={on}
              className={cn(
                'rounded-md border px-2 py-1 text-[11px] font-semibold transition-colors cursor-pointer',
                on
                  ? 'border-primary/30 bg-primary/15 text-foreground'
                  : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
              )}
            >
              {f.label}
              <span className="ml-1 font-mono text-[10px] text-muted-foreground/70">{counts[f.id] ?? 0}</span>
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto scrollbar-hide">
        {loading && rows.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 py-6">
            <DotGrid size={26} />
            <span className="text-[9px] uppercase tracking-widest text-muted-foreground/70">Loading events…</span>
          </div>
        ) : rows.length === 0 ? (
          <div className="px-3 py-4 text-[12px] italic text-muted-foreground/70">
            No {active.label.toLowerCase()} events in this window.
          </div>
        ) : (
          rows.map((e) => {
            const key = e.id ?? e.dedupKey;
            const selected = selectedKey === key;
            const sev = SEVERITY_COLORS[e.severity];
            const link = e.sources.find((s) => s.url)?.url;
            return (
              <button
                key={key}
                type="button"
                {...listNav.rowAttributes(key)}
                onClick={() => { onSelect(e); onOpen?.(e); }}
                className={cn(
                  'flex w-full items-start gap-2.5 border-b border-border/5 px-3 py-2.5 text-left transition-colors cursor-pointer',
                  selected ? 'bg-primary/10' : 'hover:bg-accent/30',
                  listNav.isSelected(key) && 'ring-1 ring-inset ring-primary/40',
                )}
              >
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: sev }} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-muted-foreground">{formatClock(e.publishedAt, tz)}</span>
                    <span
                      className="rounded-sm px-1 text-[10px] font-bold uppercase tracking-wide"
                      style={{ color: sev, backgroundColor: `${sev}1f` }}
                    >
                      {TYPE_LABEL[e.eventType] ?? e.eventType}
                    </span>
                    {e.sourceCount > 1 && (
                      <span className="font-mono text-[10px] text-muted-foreground/70">×{e.sourceCount}</span>
                    )}
                  </span>
                  <span className="mt-1 line-clamp-3 block text-[13px] font-medium leading-snug text-foreground">
                    {/* Prefer a real headline; otherwise restructure the
                        provider's synthesized actor string into a sentence. */}
                    {e.headline ?? formatEventTitle(e.title, e.placeName)}
                  </span>
                  <span className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground/70">
                    {e.countries.slice(0, 3).join(', ') || 'location unknown'}
                    {link && (
                      <a
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(ev) => ev.stopPropagation()}
                        className="text-primary/80 hover:text-primary hover:underline"
                      >
                        source
                      </a>
                    )}
                  </span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
