'use client';

// ── Demo data banner — tells the truth about seeded journal content ──────────
// The journal ships with deterministic sample trades so every tab has something
// to show on a fresh install. This banner makes that provenance explicit and
// gives the user a one-click way to remove it (which also stops it coming back).

import React, { useCallback, useEffect, useState } from 'react';
import { Database, Trash2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface DemoState {
  demoTrades: number;
  totalTrades: number;
  hasDemo: boolean;
  onlyDemo: boolean;
}

export function DemoDataBanner({ onChanged }: { onChanged?: () => void }) {
  const [state, setState] = useState<DemoState | null>(null);
  const [busy, setBusy] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await fetch('/api/journal/demo');
      if (!res.ok) return;
      setState(await res.json());
    } catch { /* banner is informational — stay hidden on failure */ }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const clear = useCallback(async () => {
    setBusy(true);
    try {
      await fetch('/api/journal/demo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'clear' }),
      });
      await load();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }, [load, onChanged]);

  if (dismissed || !state?.hasDemo) return null;

  return (
    <div className={cn(
      'mb-4 flex flex-wrap items-center gap-3 rounded-2xl border px-3.5 py-2.5 text-xs',
      'border-sky-500/20 bg-sky-500/[0.06]',
    )}>
      <span className="flex shrink-0 items-center gap-1.5 font-bold text-sky-400">
        <Database size={12} /> DEMO DATA
      </span>
      <p className="min-w-0 flex-1 text-muted-foreground">
        {state.onlyDemo
          ? `This journal is showing ${state.demoTrades} sample trades so every view has something to show.`
          : `${state.demoTrades} of ${state.totalTrades} trades are sample data; your own ${state.totalTrades - state.demoTrades} are untouched.`}
      </p>
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          type="button"
          onClick={clear}
          disabled={busy}
          className="inline-flex items-center gap-1.5 rounded-lg border border-rose-500/25 bg-rose-500/10 px-2.5 py-1 text-[10px] font-bold text-rose-400 transition-all hover:bg-rose-500/20 disabled:opacity-50 cursor-pointer"
        >
          <Trash2 size={11} /> {busy ? 'Removing…' : 'Remove demo data'}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="rounded-lg p-1 text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
          title="Dismiss"
          aria-label="Dismiss demo notice"
        >
          <X size={12} />
        </button>
      </div>
    </div>
  );
}
