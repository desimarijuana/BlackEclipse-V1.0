'use client';

// ── Investor Eye — Situation recurrence ──────────────────────────────────────
// "Is this a one-off, or the Nth incident in a run?"
//
// A single event in isolation is not intelligence: an explosion near Hormuz means
// something different when it is the fourth incident there this week. This shows
// the event's recurrence in the window — count, span, severity trend — computed
// from real stored events.
//
// Honest by construction:
//   - it counts EVENTS, never implies causation between them;
//   - "escalating" requires 3+ points and a genuinely rising trend (the module
//     enforces this; two points is a comparison, not a trend);
//   - when recurrence cannot be grouped (no anchor) or the event is outside the
//     window, it says so instead of reporting a misleading "1".

import { useEffect, useState } from 'react';
import { Layers, Loader2, TrendingUp } from 'lucide-react';
import { severityColor } from '@/lib/investor-eye/layers';
import { timeInZone } from '@/lib/investor-eye/format';
import { useDisplayTimeZone } from '@/lib/timezone';
import type { EventSeverity } from '@/lib/investor-eye/types';
import { cn } from '@/lib/utils';

interface Occurrence {
  eventId: string;
  title: string;
  severity: EventSeverity;
  publishedAt: string;
  countries: string[];
}

interface Situation {
  key: string;
  eventType: string;
  country: string;
  area: string;
  topPlace?: string;
  distinctPlaces: number;
  occurrences: Occurrence[];
  count: number;
  firstAt: string;
  lastAt: string;
  spanHours: number;
  maxSeverity: EventSeverity;
  meanSeverityWeight: number;
  severityTrend: number[];
  escalating: boolean;
}

interface SituationsResponse {
  available: boolean;
  note?: string;
  situation?: Situation;
  hours?: number;
}

function humanSpan(hours: number): string {
  if (hours < 1) return 'under an hour';
  if (hours < 48) return `${Math.round(hours)}h`;
  return `${Math.round(hours / 24)}d`;
}

export function SituationPanel({ eventId, hours }: { eventId: string; hours: number }) {
  const tz = useDisplayTimeZone();
  const [data, setData] = useState<SituationsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setData(null);
    fetch(`/api/investor-eye/situations?event=${encodeURIComponent(eventId)}&hours=${hours}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((json: SituationsResponse | null) => { if (!cancelled) setData(json); })
      .catch(() => { if (!cancelled) setData({ available: false }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eventId, hours]);

  if (loading) {
    return (
      <div>
        <Label />
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground/70">
          <Loader2 size={11} className="animate-spin" /> Counting related events…
        </div>
      </div>
    );
  }

  // A one-off is not a story — say so plainly rather than dressing up a count of 1.
  if (!data?.available || !data.situation || data.situation.count < 2) {
    return (
      <div>
        <Label />
        <div className="text-[10px] italic text-muted-foreground/70">
          {data?.note
            ?? 'No related events of this type and place in the window — a one-off so far.'}
        </div>
      </div>
    );
  }

  const s = data.situation;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <Label />
        <span className="font-mono text-[9px] text-muted-foreground">
          {data.hours ? `${Math.round(data.hours / 24)}d window` : ''}
        </span>
      </div>

      <div className="rounded-lg border border-border/25 px-2.5 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-medium text-foreground">
            {s.count}× {s.eventType.replace(/_/g, ' ')} in {s.area}
          </span>
          {s.escalating && (
            <span
              className="flex shrink-0 items-center gap-1 rounded-sm border border-amber-500/25 bg-amber-500/10 px-1.5 py-0.5 text-[9px] font-mono text-amber-300"
              title="Severity rose across three or more occurrences. A description of the trend so far — not a forecast."
            >
              <TrendingUp size={9} /> escalating
            </span>
          )}
        </div>

        <div className="mt-1 text-[9px] text-muted-foreground/70">
          over {humanSpan(s.spanHours)} · peak {s.maxSeverity}
          {/* Say plainly whether the incidents were concentrated or spread out,
              so a country-wide count is not read as one place. */}
          {s.distinctPlaces === 1 && s.topPlace
            ? ` · all at ${s.topPlace}`
            : s.distinctPlaces > 1
              ? ` · across ${s.distinctPlaces} places${s.topPlace ? `, most often ${s.topPlace}` : ''}`
              : ''}
        </div>

        {/* Severity trend — the shape of the run, from real severities. */}
        <div className="mt-1.5 flex items-end gap-0.5" aria-hidden>
          {s.severityTrend.map((w, i) => (
            <span
              key={i}
              className="w-1.5 rounded-sm"
              style={{ height: `${Math.max(3, w * 18)}px`, backgroundColor: severityColor(sevFromWeight(w)) }}
            />
          ))}
        </div>

        <div className="mt-1.5 space-y-0.5">
          {s.occurrences.slice(0, 5).map((o) => (
            <div key={o.eventId} className="flex items-start gap-1.5">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: severityColor(o.severity) }} />
              <span className="min-w-0 flex-1 truncate text-[9px] text-muted-foreground">{o.title}</span>
              <span className="shrink-0 font-mono text-[9px] text-muted-foreground/60">
                {timeInZone(o.publishedAt, tz)}
              </span>
            </div>
          ))}
          {s.count > 5 && (
            <div className="text-[9px] text-muted-foreground/60">+{s.count - 5} more in this window</div>
          )}
        </div>
      </div>

      <div className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
        Counted from events in this window. Co-location in time and place only — not a claim that they are related.
      </div>
    </div>
  );
}

/** Map a 0..1 severity weight back to a band, for the trend bar colour. */
function sevFromWeight(w: number): EventSeverity {
  if (w >= 0.9) return 'critical';
  if (w >= 0.6) return 'high';
  if (w >= 0.35) return 'medium';
  return 'low';
}

function Label() {
  return (
    <div className={cn('mb-1 flex items-center gap-1.5', 'text-[9px] font-bold uppercase tracking-widest text-muted-foreground')}>
      <Layers size={10} /> Situation
    </div>
  );
}
