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

import { useMemo, useState } from 'react';
import { Radio } from 'lucide-react';
import { DotGrid } from '@/components/ui/ascii-loader';
import type { NormalizedEvent } from '@/lib/investor-eye/types';
import { SEVERITY_COLORS } from '@/lib/investor-eye/layers';
import { formatUtc, formatEventTitle } from '@/lib/investor-eye/format';
import { cn } from '@/lib/utils';

interface LiveFeedProps {
  events: NormalizedEvent[];
  onSelect: (event: NormalizedEvent) => void;
  selectedKey?: string;
  /** True while the first world-state fetch is still in flight. */
  loading?: boolean;
  className?: string;
}

/** Feed lenses. `conflict` is first because it is the primary use case. */
const FILTERS: Array<{ id: 'conflict' | 'all' | 'energy' | 'trade' | 'disaster'; label: string; types: string[] | null }> = [
  { id: 'conflict', label: 'Conflict', types: ['conflict', 'military', 'protest'] },
  { id: 'all', label: 'All', types: null },
  { id: 'energy', label: 'Energy', types: ['energy'] },
  { id: 'trade', label: 'Trade', types: ['trade', 'tariff', 'shipping', 'sanction'] },
  { id: 'disaster', label: 'Hazards', types: ['natural_disaster'] },
];

type FilterId = (typeof FILTERS)[number]['id'];

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

export function LiveFeed({ events, onSelect, selectedKey, loading = false, className }: LiveFeedProps) {
  const [filter, setFilter] = useState<FilterId>('conflict');

  const active = FILTERS.find((f) => f.id === filter) ?? FILTERS[0];

  const rows = useMemo(() => {
    const types = active.types;
    const list = types ? events.filter((e) => types.includes(e.eventType)) : events;
    // Newest first; the state is already window-filtered by the timeline.
    return [...list].sort((a, b) => Date.parse(b.publishedAt) - Date.parse(a.publishedAt)).slice(0, 60);
  }, [events, active]);

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const f of FILTERS) {
      const types = f.types;
      out[f.id] = types ? events.filter((e) => types.includes(e.eventType)).length : events.length;
    }
    return out;
  }, [events]);

  return (
    <div className={cn('flex min-h-0 flex-col rounded-2xl border border-white/10 dark:border-white/5 glass-card', className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border/10 px-3 py-2">
        <div className="flex items-center gap-1.5">
          <Radio size={12} className="text-emerald-400" />
          <span className="text-[9px] font-bold uppercase tracking-widest text-foreground">Live Event Stream</span>
        </div>
        <span className="font-mono text-[9px] text-muted-foreground">{rows.length}</span>
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
                'rounded-md border px-1.5 py-0.5 text-[9px] font-semibold transition-colors cursor-pointer',
                on
                  ? 'border-primary/30 bg-primary/15 text-foreground'
                  : 'border-transparent text-muted-foreground hover:bg-accent/40 hover:text-foreground',
              )}
            >
              {f.label}
              <span className="ml-1 font-mono text-[8px] text-muted-foreground/70">{counts[f.id] ?? 0}</span>
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
          <div className="px-3 py-4 text-[10px] italic text-muted-foreground/70">
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
                onClick={() => onSelect(e)}
                className={cn(
                  'flex w-full items-start gap-2 border-b border-border/5 px-3 py-1.5 text-left transition-colors cursor-pointer',
                  selected ? 'bg-primary/10' : 'hover:bg-accent/30',
                )}
              >
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: sev }} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-[9px] text-muted-foreground">{formatUtc(e.publishedAt).slice(11, 16)}</span>
                    <span
                      className="rounded-sm px-1 text-[8px] font-bold uppercase tracking-wide"
                      style={{ color: sev, backgroundColor: `${sev}1f` }}
                    >
                      {TYPE_LABEL[e.eventType] ?? e.eventType}
                    </span>
                    {e.sourceCount > 1 && (
                      <span className="font-mono text-[8px] text-muted-foreground/70">×{e.sourceCount}</span>
                    )}
                  </span>
                  <span className="mt-0.5 line-clamp-2 block text-[10px] leading-snug text-foreground">
                    {/* Prefer a real headline; otherwise restructure the
                        provider's synthesized actor string into a sentence. */}
                    {e.headline ?? formatEventTitle(e.title, e.placeName)}
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5 text-[9px] text-muted-foreground/70">
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
