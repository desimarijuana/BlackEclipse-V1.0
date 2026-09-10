'use client';

// ── DashboardOnboarding — first-run persona picker ───────────────────────────
// Asks what the user uses BlackEclipse for, then seeds a starting template.
// The template is ONLY a starting point — the user can fully modify it.

import React, { useState } from 'react';
import {
  BarChart3, Briefcase, Coins, Globe, LineChart, Orbit, Search, Wallet,
} from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { DASHBOARD_TEMPLATES } from '@/lib/dashboard/templates';

const PERSONA_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  trader: LineChart,
  investor: Briefcase,
  crypto: Coins,
  forex: Globe,
  quant: BarChart3,
  macro: Orbit,
  research: Search,
};

export interface OnboardingResult {
  templateId: string;
  name: string;
}

export function DashboardOnboarding({
  open,
  onComplete,
}: {
  open: boolean;
  onComplete: (result: OnboardingResult) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);

  return (
    <Dialog open={open} onOpenChange={() => { /* modal — no dismiss */ }}>
      <DialogContent
        showCloseButton={false}
        className="w-[calc(100%-2rem)] max-w-2xl rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-0 gap-0 overflow-hidden"
      >
        <DialogTitle className="sr-only">Build your workspace</DialogTitle>
        <div className="p-6">
          <h2 className="font-serif text-xl font-semibold text-foreground">Build your workspace</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            What do you use BlackEclipse for? We&apos;ll set up a starting template — you can change everything later.
          </p>

          <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 gap-2.5">
            {DASHBOARD_TEMPLATES.map(t => {
              const Icon = PERSONA_ICON[t.id] ?? Wallet;
              const isSel = selected === t.id;
              return (
                <button
                  key={t.id}
                  onClick={() => setSelected(t.id)}
                  className={cn(
                    'flex flex-col items-start gap-2 rounded-2xl border p-3.5 text-left transition-all cursor-pointer',
                    isSel
                      ? 'border-primary/50 bg-primary/10'
                      : 'border-white/10 dark:border-white/10 glass-card-subtle hover:border-primary/40 hover:bg-accent/40',
                  )}
                >
                  <span className={cn('flex h-9 w-9 items-center justify-center rounded-xl border',
                    isSel ? 'border-primary/40 bg-primary/15 text-primary' : 'border-border/40 bg-accent/40 text-muted-foreground')}>
                    <Icon size={16} />
                  </span>
                  <span className="text-sm font-bold text-foreground">{t.name}</span>
                  <span className="text-[10px] text-muted-foreground leading-snug">{t.desc}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/10 px-6 py-4">
          <button
            onClick={() => onComplete({ templateId: selected ?? 'trader', name: selected ?? 'Trader' })}
            disabled={!selected}
            className={cn(
              'rounded-xl border px-4 py-2 text-xs font-bold transition-all cursor-pointer',
              selected
                ? 'border-primary/40 bg-primary/15 text-primary hover:bg-primary/25'
                : 'border-border/40 bg-accent/30 text-muted-foreground opacity-40 cursor-not-allowed',
            )}
          >
            Build workspace
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
