'use client';

// ── Investor Eye — Event Detail Panel ────────────────────────────────────────
// Shows the observed facts separately from potential exposure, exactly as the
// spec requires (spec §18). Provenance links are real; nothing is fabricated.

import { X } from 'lucide-react';
import { severityColor } from '@/lib/investor-eye/layers';
import { formatUtc } from '@/lib/investor-eye/format';
import type { NormalizedEvent } from '@/lib/investor-eye/types';

interface EventPanelProps {
  event: NormalizedEvent;
  onClose: () => void;
  onSelectCountry?: (iso2: string) => void;
}

export function EventPanel({ event, onClose, onSelectCountry }: EventPanelProps) {
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex items-start justify-between gap-2 border-b border-border/10 px-4 py-3">
        <div className="min-w-0">
          <div className="mb-1 flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: severityColor(event.severity) }} />
            <span className="text-[10px] font-mono uppercase tracking-wide text-muted-foreground">
              {event.eventType.replace(/_/g, ' ')} · {event.severity}
            </span>
          </div>
          <div className="text-sm font-semibold leading-snug text-foreground">{event.title}</div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-lg p-1 text-muted-foreground hover:bg-accent hover:text-foreground cursor-pointer"
          aria-label="Close event panel"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4 scrollbar-hide">
        {event.summary && <p className="text-[11px] leading-relaxed text-muted-foreground">{event.summary}</p>}

        <Block title="Observed">
          <Row label="First detected" value={formatUtc(event.publishedAt)} />
          <Row label="Last updated" value={event.lastUpdated ? formatUtc(event.lastUpdated) : '—'} />
          <Row label="Sources" value={String(event.sourceCount)} />
          <Row label="Data confidence" value={event.confidence.toFixed(2)} />
          <Row label="Primary source" value={event.primarySource} />
          {event.countries.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {event.countries.map((c) => (
                <button
                  key={c}
                  onClick={() => onSelectCountry?.(c)}
                  className="glass-card-subtle rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] font-mono text-foreground hover:border-primary/30 cursor-pointer"
                >
                  {c}
                </button>
              ))}
            </div>
          )}
        </Block>

        {(event.channels.length > 0 || event.commodities.length > 0 || event.sectors.length > 0) && (
          <Block title="Potential exposure" hint="Derived from the event text — not a causal claim.">
            {event.channels.length > 0 && <Row label="Economic channels" value={event.channels.join(', ')} />}
            {event.commodities.length > 0 && <Row label="Commodities" value={event.commodities.join(', ')} />}
            {event.sectors.length > 0 && <Row label="Sectors" value={event.sectors.join(', ')} />}
          </Block>
        )}

        <Block title="Evidence">
          {event.sources.length === 0 ? (
            <div className="text-[10px] italic text-muted-foreground/70">No source list captured.</div>
          ) : (
            <div className="space-y-1">
              {event.sources.slice(0, 10).map((s, i) => (
                <div key={`${s.id}-${i}`} className="text-[10px]">
                  <span className="text-muted-foreground">{s.name}</span>
                  {s.publishedAt ? <span className="text-muted-foreground/60"> · {formatUtc(s.publishedAt)}</span> : null}
                  {s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="ml-1 text-primary hover:underline break-all"
                    >
                      open
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </Block>

        <div className="rounded-lg border border-border/30 px-2.5 py-2 text-[10px] leading-relaxed text-muted-foreground/80">
          Confidence is internal data quality (how well the event is corroborated and located), not a
          probability that the event is true. Market interpretations are never shown as facts.
        </div>
      </div>
    </div>
  );
}

function Block({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{title}</div>
      {hint && <div className="mb-1 text-[9px] italic text-muted-foreground/70">{hint}</div>}
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-0.5">
      <span className="text-[10px] text-muted-foreground">{label}</span>
      <span className="text-right text-[10px] font-medium text-foreground">{value}</span>
    </div>
  );
}
