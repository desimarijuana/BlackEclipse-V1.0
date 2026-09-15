'use client';

// ── Investor Eye — Risk decomposition panel (Phase 2) ────────────────────────
// No single arbitrary "risk score": each dimension is shown with its own bar,
// drivers and sample size so the number is always explainable (spec §39).

import { useTopic } from '@/lib/workspace/data-hub';
import { IE_RISK_TOPIC } from '@/lib/investor-eye/topics';
import type { RiskComponent, RegionState, Transmission } from '@/lib/investor-eye/analytics';
import { cn } from '@/lib/utils';

interface RiskPayload {
  components: RiskComponent[];
  regions: RegionState[];
  transmissions: Transmission[];
  eventCount: number;
  provenance: string;
}

export function RiskPanel() {
  const topic = useTopic<RiskPayload>(IE_RISK_TOPIC);
  const data = topic.data;

  if (topic.source === 'UNAVAILABLE' || !data) {
    return <PanelShell title="Risk"><Muted>Risk decomposition unavailable.</Muted></PanelShell>;
  }

  return (
    <PanelShell title="Risk Dimensions">
      <div className="space-y-2">
        {data.components.map((c) => (
          <div key={c.id}>
            <div className="flex items-center justify-between text-[10px]">
              <span className="text-muted-foreground">{c.label}</span>
              <span className="font-mono text-foreground">{(c.score * 100).toFixed(0)}</span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/[0.06]">
              <div
                className={cn('h-full rounded-full', c.score >= 0.66 ? 'bg-red-500' : c.score >= 0.33 ? 'bg-amber-500' : 'bg-emerald-500')}
                style={{ width: `${Math.max(2, c.score * 100)}%` }}
              />
            </div>
            <div className="mt-0.5 text-[9px] text-muted-foreground/60">
              {c.sampleSize} event{c.sampleSize === 1 ? '' : 's'}
              {c.drivers.length > 0 ? ` · ${c.drivers.slice(0, 2).join(' · ')}` : ''}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 border-t border-border/10 pt-1.5 text-[9px] italic text-muted-foreground/60">
        Scores are decomposable event-density measures, not a market forecast.
      </div>
    </PanelShell>
  );
}

function PanelShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2.5">
      <div className="mb-2 text-[9px] font-bold uppercase tracking-widest text-muted-foreground">{title}</div>
      {children}
    </div>
  );
}

function Muted({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] italic text-muted-foreground/70">{children}</div>;
}
