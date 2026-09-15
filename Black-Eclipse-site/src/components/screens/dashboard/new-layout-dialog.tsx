'use client';

// ── NewLayoutDialog — create a layout from a preset ──────────────────────────
// Opened from the Command Center's "New layout" button. A frosted-glass, portaled
// dialog (so it is never clipped by the tab bar's scroll container) where the
// user names the layout AND picks a starting preset in one step — saving the
// extra trip through the workspace's Templates menu.

import React, { useState } from 'react';
import {
  BarChart3, Briefcase, Coins, Globe, LineChart, LayoutGrid, Orbit, Search,
} from 'lucide-react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import { DASHBOARD_TEMPLATES } from '@/lib/dashboard/templates';

const PRESET_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  trader: LineChart,
  investor: Briefcase,
  crypto: Coins,
  forex: Globe,
  quant: BarChart3,
  macro: Orbit,
  research: Search,
};

const INPUT_CLS = 'w-full rounded-xl border border-border/40 bg-background/60 px-3 py-2.5 text-xs font-semibold text-foreground outline-none transition-colors placeholder:text-muted-foreground/50 hover:border-primary/50 focus:border-primary/50 focus:ring-1 focus:ring-primary';

export function NewLayoutDialog({
  defaultName,
  onClose,
  onCreate,
}: {
  defaultName: string;
  onClose: () => void;
  onCreate: (name: string, templateId: string) => void;
}) {
  const [name, setName] = useState(defaultName);
  const [preset, setPreset] = useState(DASHBOARD_TEMPLATES[0]?.id ?? 'trader');

  const submit = () => onCreate(name.trim() || defaultName, preset);

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="w-[calc(100%-2rem)] max-w-lg rounded-2xl border border-white/15 dark:border-white/10 glass-card-strong p-0 gap-0 overflow-hidden">
        <DialogTitle className="sr-only">New layout</DialogTitle>

        <div className="p-5">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/15 text-primary">
              <LayoutGrid size={18} />
            </span>
            <div className="min-w-0">
              <h2 className="font-serif text-lg font-semibold text-foreground">New layout</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Give it a name and pick a starting preset. You can rearrange every widget afterwards.
              </p>
            </div>
          </div>

          <div className="mt-5">
            <label className="block text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
              Layout name
            </label>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              onFocus={e => e.currentTarget.select()}
              onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); submit(); } }}
              placeholder="e.g. My Tech Sheet"
              className={cn(INPUT_CLS, 'mt-1.5')}
            />
          </div>

          <div className="mt-5">
            <label className="block text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
              Starting preset
            </label>
            <div className="mt-2 grid max-h-[19rem] grid-cols-2 gap-2 overflow-y-auto scrollbar-hide sm:grid-cols-3">
              {DASHBOARD_TEMPLATES.map(t => {
                const Icon = PRESET_ICON[t.id] ?? LayoutGrid;
                const sel = preset === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setPreset(t.id)}
                    className={cn(
                      'flex flex-col items-start gap-2 rounded-2xl border p-3 text-left transition-all cursor-pointer',
                      sel
                        ? 'border-primary/50 bg-primary/10'
                        : 'border-white/10 dark:border-white/10 glass-card-subtle hover:border-primary/40 hover:bg-accent/40',
                    )}
                  >
                    <span className={cn(
                      'flex h-8 w-8 items-center justify-center rounded-xl border',
                      sel ? 'border-primary/40 bg-primary/15 text-primary' : 'border-border/40 bg-accent/40 text-muted-foreground',
                    )}>
                      <Icon size={15} />
                    </span>
                    <span className="text-xs font-bold text-foreground">{t.name}</span>
                    <span className="text-[9px] leading-snug text-muted-foreground line-clamp-2">{t.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border/10 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center justify-center rounded-xl border border-border/40 bg-accent/30 px-4 py-2 text-xs font-bold text-muted-foreground transition-all hover:border-primary/40 hover:text-primary cursor-pointer"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            className="inline-flex items-center justify-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 px-4 py-2 text-xs font-bold text-primary transition-all hover:bg-primary/25 cursor-pointer"
          >
            <LayoutGrid size={12} /> Create layout
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
