'use client';

// ── Studio header ───────────────────────────────────────────────────────────
// Title, the bound strategy, the share link and refresh. Kept out of the screen
// so the screen stays about the workspace itself.

import React from 'react';
import { DesktopOnlyNotice } from '@/components/ui/desktop-only-notice';
import type { StrategyRecord } from '@/lib/backtest/backtest-client';
import { Activity, Check, Link2, Loader2 } from '@/lib/icons';

export function StudioHeader({
  saved,
  loading,
  linkCopied,
  onShare,
  onRefresh,
}: {
  saved: StrategyRecord | null;
  loading: boolean;
  linkCopied: boolean;
  onShare: () => void;
  onRefresh: () => void;
}) {
  return (
    <>
      <DesktopOnlyNotice title="Strategy Studio" />

      <div className="glass-card flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
        <span className="h-6 w-1 shrink-0 rounded-full bg-primary" />
        <div className="min-w-0 flex-1">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-foreground">Strategy Studio</h1>
          <p className="font-mono text-[10px] text-muted-foreground">
            Prompt -&gt; spec -&gt; deterministic backtest -&gt; robustness -&gt; paper. Engine: Python quant runtime.
          </p>
        </div>
        {saved ? (
          <span className="rounded-md border border-emerald-500/30 px-2 py-0.5 font-mono text-[10px] text-emerald-400">
            {saved.name || saved.id} · v{saved.version ?? saved.latestVersion}
          </span>
        ) : null}
        <button
          type="button"
          onClick={onShare}
          disabled={!saved}
          title="Copy a link that reopens this strategy and experiment"
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs disabled:opacity-40"
        >
          {linkCopied ? <Check className="h-3.5 w-3.5" /> : <Link2 className="h-3.5 w-3.5" />}
          {linkCopied ? 'Copied' : 'Share'}
        </button>
        <button
          type="button"
          onClick={onRefresh}
          className="glass-button flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs"
        >
          {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
          Refresh
        </button>
      </div>
    </>
  );
}
