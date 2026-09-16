'use client';

// ── Investor Eye — Market Transmission panel (Phase 2.8, spec §37) ───────────
// Renders the transmission chains already computed by `/api/investor-eye/risk`
// (previously dead data). Each step's relation class is shown explicitly so an
// inference is never read as a fact:
//
//   Event → Country → Economic channel → Asset (observed print)
//
// The channel→asset hop is INFERRED (a documented rule); the event, country and
// asset print are OBSERVED.

import { ArrowRight } from 'lucide-react';
import { useTopic } from '@/lib/workspace/data-hub';
import { IE_RISK_TOPIC } from '@/lib/investor-eye/topics';
import type { Transmission } from '@/lib/investor-eye/analytics';
import type { RelationClass } from '@/lib/investor-eye/types';
import { cn } from '@/lib/utils';

const CLASS_STYLE: Record<RelationClass, string> = {
  OBSERVED: 'border-emerald-500/30 text-emerald-400',
  HISTORICAL: 'border-violet-500/30 text-violet-400',
  INFERRED: 'border-amber-500/30 text-amber-400',
  'AI-INTERPRETED': 'border-fuchsia-500/30 text-fuchsia-400',
};

interface RiskPayload {
  transmissions: Transmission[];
  provenance: string;
}

export function TransmissionsPanel() {
  const topic = useTopic<RiskPayload>(IE_RISK_TOPIC);
  const transmissions = topic.data?.transmissions ?? [];

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Market Transmission
        </span>
        <span className="text-[9px] font-mono text-muted-foreground/60">{transmissions.length}</span>
      </div>

      {topic.source === 'UNAVAILABLE' && (
        <div className="text-[10px] italic text-muted-foreground/70">Transmissions unavailable.</div>
      )}

      {topic.source !== 'UNAVAILABLE' && transmissions.length === 0 && (
        <div className="text-[10px] italic text-muted-foreground/70">
          No transmission chains in this window — no events carried a mapped economic channel.
        </div>
      )}

      <div className="space-y-2">
        {transmissions.slice(0, 4).map((t) => (
          <div key={t.eventId} className="rounded-lg border border-border/20 px-2 py-1.5">
            <div className="line-clamp-2 text-[10px] font-medium text-foreground/90">{t.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1">
              {t.steps.slice(0, 6).map((step, i) => (
                <span key={i} className="flex items-center gap-1">
                  {i > 0 && <ArrowRight size={9} className="shrink-0 text-muted-foreground/40" />}
                  <span
                    className={cn(
                      'rounded border px-1 py-0.5 text-[9px] font-medium',
                      CLASS_STYLE[step.relation],
                    )}
                    title={`${step.kind} · ${step.relation}${step.detail ? ` · ${step.detail}` : ''}`}
                  >
                    {step.label.length > 26 ? `${step.label.slice(0, 26)}…` : step.label}
                    {step.detail ? <span className="ml-1 font-mono opacity-80">{step.detail}</span> : null}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {transmissions.length > 0 && (
        <div className="mt-2 border-t border-border/10 pt-1.5 text-[9px] italic leading-relaxed text-muted-foreground/60">
          Channel and asset links are <span className="text-amber-400">INFERRED</span> from an explicit
          rule — they are potential exposure, not causality. Event, country and price prints are observed.
        </div>
      )}
    </div>
  );
}
