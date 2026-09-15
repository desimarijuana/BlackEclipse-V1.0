'use client';

// ── Investor Eye — Country Intelligence Panel ────────────────────────────────
// The right-side panel opened by clicking a country. It shows only fields with
// real data: events, markets (from the assembled state) and economic metrics
// (from the real fetch layer). Missing data is stated, never zero-filled.

import { useEffect, useState } from 'react';
import { X, Loader2 } from 'lucide-react';
import type { NormalizedEvent, Provenance } from '@/lib/investor-eye/types';
import { severityColor } from '@/lib/investor-eye/layers';
import { cn } from '@/lib/utils';

interface CountryPanelProps {
  iso2: string;
  name: string;
  hours: number;
  onClose: () => void;
  onSelectEvent: (event: NormalizedEvent) => void;
}

interface Metric {
  id: string;
  label: string;
  value: number;
  unit: string;
  asOf: string | null;
}

interface CountryResponse {
  country: { iso2: string; name: string; region?: string; marketId?: string; currency?: string };
  events: NormalizedEvent[];
  eventCount: number;
  metrics: Metric[];
  metricsProvenance: Provenance;
  windowHours: number;
}

export function CountryPanel({ iso2, name, hours, onClose, onSelectEvent }: CountryPanelProps) {
  const [data, setData] = useState<CountryResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/investor-eye/countries/${encodeURIComponent(iso2)}?hours=${Math.max(hours, 168)}`)
      .then((r) => r.json())
      .then((json: CountryResponse) => {
        if (!cancelled) setData(json);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [iso2, hours]);

  const byType = new Map<string, number>();
  for (const e of data?.events ?? []) byType.set(e.eventType, (byType.get(e.eventType) ?? 0) + 1);
  const topTypes = [...byType.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/10 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">{data?.country.name ?? name}</div>
          <div className="text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
            {iso2}
            {data?.country.region ? ` · ${data.country.region}` : ''}
            {data?.country.currency ? ` · ${data.country.currency}` : ''}
          </div>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
          aria-label="Close country panel"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 scrollbar-hide">
        {loading && (
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Loading intelligence…
          </div>
        )}

        {!loading && (
          <>
            <Section title="Events" count={data?.eventCount ?? 0}>
              {topTypes.length === 0 ? (
                <Empty text="No events in the selected window." />
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {topTypes.map(([type, count]) => (
                    <span key={type} className="glass-card-subtle rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {type.replace(/_/g, ' ')} · {count}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-2 space-y-1">
                {(data?.events ?? []).slice(0, 8).map((e) => (
                  <button
                    key={e.id ?? e.dedupKey}
                    onClick={() => onSelectEvent(e)}
                    className="flex w-full items-start gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-accent/40 cursor-pointer"
                  >
                    <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: severityColor(e.severity) }} />
                    <span className="line-clamp-2 text-[11px] text-foreground/90">{e.title}</span>
                  </button>
                ))}
              </div>
            </Section>

            <Section title="Economy" count={data?.metrics.length ?? 0}>
              {(data?.metrics.length ?? 0) === 0 ? (
                <Empty text="No economic series available for this country from free public sources." />
              ) : (
                <div className="grid grid-cols-2 gap-1.5">
                  {data?.metrics.map((m) => (
                    <div key={m.id} className="glass-card-subtle rounded-lg border border-white/10 px-2 py-1.5">
                      <div className="text-[9px] uppercase tracking-wide text-muted-foreground">{m.label}</div>
                      <div className="text-[13px] font-semibold text-foreground">
                        {m.value}{m.unit ? <span className="text-[10px] text-muted-foreground">{m.unit}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Section>

            <Section title="Trade & Market Link" count={data?.country.marketId ? 1 : 0}>
              {data?.country.marketId ? (
                <div className="text-[11px] text-muted-foreground">
                  Linked JDDS market: <span className="font-mono text-foreground">{data.country.marketId}</span>
                  <div className="mt-1 text-[10px]">
                    Market observations for this country appear on the Markets layer.
                  </div>
                </div>
              ) : (
                <Empty text="No JDDS market is linked to this country." />
              )}
            </Section>
          </>
        )}
      </div>
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{title}</span>
        <span className={cn('rounded-sm border px-1 text-[9px] font-mono', count > 0 ? 'border-primary/30 text-primary' : 'border-border/40 text-muted-foreground/60')}>
          {count}
        </span>
      </div>
      {children}
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="text-[10px] italic text-muted-foreground/70">{text}</div>;
}
