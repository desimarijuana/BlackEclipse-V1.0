'use client';

// ── Investor Eye — Price Reaction ────────────────────────────────────────────
// Shows what the relevant instrument ACTUALLY did after an event, measured from
// stored daily closes. This is the observable counterpart to "potential
// exposure": the exposure block says what COULD matter, this says what the
// market did.
//
// Real data or nothing: an unmeasurable window renders an explicit reason
// rather than a dash that could be mistaken for "no move".

import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Minus } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { reactionWindowLabel, type ReactionWindow } from '@/lib/investor-eye/reaction';

interface ReactionResponse {
  available: boolean;
  note?: string;
  symbol?: string;
  eventDate?: string | null;
  reaction?: {
    symbol: string;
    baseline: { date: string; value: number } | null;
    measures: Array<{ window: ReactionWindow; changePct: number; from: string; to: string }>;
    maxAbsChangePct: number | null;
    daysAfter: number;
    availability: string;
    note: string;
  };
}

export function ReactionPanel({ eventId, symbol }: { eventId: string; symbol?: string }) {
  const [data, setData] = useState<ReactionResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const qs = new URLSearchParams({ id: eventId });
    if (symbol) qs.set('symbol', symbol);
    fetch(`/api/investor-eye/reaction?${qs}`)
      .then((r) => r.json())
      .then((json: ReactionResponse) => { if (!cancelled) setData(json); })
      .catch(() => { if (!cancelled) setData({ available: false, note: 'Price reaction unavailable.' }); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eventId, symbol]);

  if (loading) {
    return (
      <div>
        <BlockLabel>Market reaction</BlockLabel>
        <div className="text-[10px] text-muted-foreground/70">Measuring stored closes…</div>
      </div>
    );
  }

  if (!data?.available || !data.reaction) {
    return (
      <div>
        <BlockLabel>Market reaction</BlockLabel>
        <div className="text-[10px] italic text-muted-foreground/70">
          {data?.note ?? 'No measurable reaction — history does not cover this window.'}
        </div>
      </div>
    );
  }

  const r = data.reaction;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <BlockLabel>Market reaction</BlockLabel>
        <span className="font-mono text-[9px] text-muted-foreground">{r.symbol}</span>
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        {r.measures.map((m) => {
          const up = m.changePct > 0;
          const flat = m.changePct === 0;
          const Icon = flat ? Minus : up ? TrendingUp : TrendingDown;
          return (
            <div
              key={m.window}
              className="glass-card-subtle rounded-lg border border-white/10 px-2 py-1.5"
              title={`${m.from} → ${m.to}`}
            >
              <div className="text-[8px] font-bold uppercase tracking-widest text-muted-foreground/70">
                {reactionWindowLabel(m.window)}
              </div>
              <div
                className={cn(
                  'mt-0.5 flex items-center gap-1 font-mono text-[13px] font-semibold',
                  flat ? 'text-muted-foreground' : up ? 'text-emerald-400' : 'text-red-400',
                )}
              >
                <Icon size={11} />
                {up ? '+' : ''}{m.changePct.toFixed(2)}%
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[9px] text-muted-foreground/70">
        {r.baseline && <span>baseline {r.baseline.date} @ {r.baseline.value.toFixed(2)}</span>}
        <span>· {r.daysAfter} sessions of history after the event</span>
      </div>
      <div className="mt-1 text-[9px] italic leading-relaxed text-muted-foreground/60">{r.note}</div>
    </div>
  );
}

function BlockLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{children}</div>
  );
}
